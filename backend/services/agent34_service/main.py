from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from PIL import Image
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend.agents.agent3.src.verified_package_bridge import enrich_verified_package
from .auth import require_bearer
from .request_builder import build_requests
from .runtime_manager import RuntimeManager
from .schemas import ReportPayload, VerifyPayload
from .settings import Settings


CONTRACT_VERSION = "agent34-http-1.0"
PIPELINE_VERSION = "competition-four-agent-v1"


def _error(code: str, message: str, retryable: bool, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "retryable": retryable},
    )


def _markdown(report: dict[str, Any], lang: str) -> str:
    from backend.agents.agent4.src.renderers_separate import render_markdown_language
    with tempfile.TemporaryDirectory(prefix="agent4_markdown_") as temp:
        target = Path(temp) / ("report_zh.md" if lang == "zh-CN" else "report_en.md")
        render_markdown_language(report, [], target, lang)
        return target.read_text(encoding="utf-8")


async def _multipart(request: Request) -> tuple[VerifyPayload, dict[str, bytes]]:
    form = await request.form()
    payload_part = form.get("payload")
    if payload_part is None:
        raise _error("INVALID_REQUEST", "multipart payload is required", False, 422)
    try:
        if isinstance(payload_part, UploadFile):
            raw_payload = (await payload_part.read()).decode("utf-8")
        else:
            raw_payload = str(payload_part)
        payload = VerifyPayload.model_validate(json.loads(raw_payload))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise _error("INVALID_REQUEST", "payload is not valid Agent3 JSON", False, 422) from exc

    result: dict[str, bytes] = {}
    for name in (
        "pre_image", "post_image", "damage_map", "fused_overlay",
        "road_status_map", "building_instance_mask",
    ):
        part = form.get(name)
        if part is None:
            if name in {"pre_image", "post_image"}:
                raise _error("INVALID_REQUEST", f"{name} is required", False, 422)
            continue
        if not isinstance(part, UploadFile):
            raise _error("INVALID_REQUEST", f"{name} must be a file", False, 422)
        data = await part.read()
        try:
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
        except Exception as exc:
            raise _error("IMAGE_DECODE_FAILED", f"{name} cannot be decoded", False, 422) from exc
        result[name] = data
    return payload, result


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Agent34 Service", version="1.0.0")
    app.state.settings = settings or Settings.from_env()
    app.state.settings.request_root.mkdir(parents=True, exist_ok=True)
    app.state.runtime = RuntimeManager(app.state.settings)

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = exc.detail
        else:
            body = {
                "code": "UNAUTHORIZED" if exc.status_code == 401 else "INVALID_REQUEST",
                "message": "authentication failed" if exc.status_code == 401 else "request failed",
                "retryable": False,
            }
        return JSONResponse(status_code=exc.status_code, content={"error": body})

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_REQUEST", "message": "request validation failed", "retryable": False}},
        )

    @app.get("/api/v1/health")
    def health():
        runtime = app.state.runtime.health()
        configured = app.state.settings.runtime_mode == "mock" or bool(
            app.state.settings.agent3_base_model
            and app.state.settings.agent3_adapter
            and app.state.settings.agent4_base_model
            and app.state.settings.agent4_adapter
        )
        return {
            "status": "ok",
            "service_version": "agent34-service-1.0",
            "contract_version": CONTRACT_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "agent3_ready": configured,
            "agent4_ready": configured,
            "max_concurrency": 1,
            "runtime": runtime,
        }

    @app.post("/api/v1/agent3/verify", dependencies=[Depends(require_bearer)])
    async def verify(request: Request):
        parsed, uploaded = await _multipart(request)
        work = Path(tempfile.mkdtemp(prefix=f"{parsed.job_id}_{parsed.sample_id}_", dir=app.state.settings.request_root))
        try:
            assets: dict[str, Path] = {}
            for name, data in uploaded.items():
                target = work / f"{name}.png"
                target.write_bytes(data)
                assets[name] = target
            requests = build_requests(parsed, assets, work)
            if not app.state.runtime.lock.acquire(blocking=False):
                raise _error("SERVICE_BUSY", "Agent34 runtime is busy", True, 503)
            try:
                package = app.state.runtime.agent3().verify_batch(requests)
            finally:
                app.state.runtime.lock.release()
            package = enrich_verified_package(
                package,
                sample_id=parsed.sample_id,
                claim_list=[item.model_dump() for item in parsed.claim_list],
            )
            return {
                "contract_version": CONTRACT_VERSION,
                "pipeline_version": PIPELINE_VERSION,
                "job_id": parsed.job_id,
                "sample_id": parsed.sample_id,
                "agent_code": "agent3",
                "capability": "evidence_verification",
                "source_version": "Agent3-V5.2",
                "runtime_version": "agent3-v5.2-runtime-3.1",
                "status": "succeeded",
                "check_result": package.get("audit_records", []),
                "verified_evidence_package": package,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @app.post("/api/v1/agent4/report", dependencies=[Depends(require_bearer)])
    def report(payload: ReportPayload):
        from backend.agents.agent4.src.validate_report import validate_report
        if not app.state.runtime.lock.acquire(blocking=False):
            raise _error("SERVICE_BUSY", "Agent34 runtime is busy", True, 503)
        try:
            platform_report = app.state.runtime.agent4().generate_report(payload.verified_evidence_package)
        finally:
            app.state.runtime.lock.release()
        schema = Path(__file__).resolve().parents[2] / "agents" / "agent4" / "src" / "platform_report_schema_v3.json"
        errors = validate_report(platform_report, schema)
        if errors:
            raise _error("MODEL_OUTPUT_INVALID", "Agent4 output failed schema validation", False, 502)
        markdown_zh = _markdown(platform_report, "zh-CN")
        markdown_en = _markdown(platform_report, "en-US")
        return {
            "contract_version": CONTRACT_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "job_id": payload.job_id,
            "sample_id": payload.sample_id,
            "agent_code": "agent4",
            "capability": "report_generation",
            "source_version": "Agent4-V3",
            "runtime_version": "agent4-v3",
            "status": "succeeded",
            "platform_report_json": platform_report,
            "markdown_report_zh": markdown_zh,
            "markdown_report_en": markdown_en,
            "markdown_report": markdown_zh,
        }

    return app


app = create_app()
