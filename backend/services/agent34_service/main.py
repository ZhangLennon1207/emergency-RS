from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import ValidationError
from starlette.datastructures import UploadFile

from backend.agents.agent3.src.verified_package_bridge import enrich_verified_package
from .auth import require_bearer
from .artifact_store import persist_second_check_artifacts, resolve_artifact
from .audit_privacy import persist_private_outputs, public_package
from .errors import ERRORS, runtime_code, service_error, validation_code
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


def _runtime_error(exc: Exception) -> HTTPException:
    return service_error(runtime_code(exc))


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
    except ValidationError as exc:
        raise service_error(validation_code(exc)) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise service_error("INVALID_REQUEST") from exc

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
            raise service_error("IMAGE_DECODE_FAILED") from exc
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
    async def validation_error(_request: Request, exc: RequestValidationError):
        code = "EMPTY_CLAIM_LIST" if any(
            "claim_list" in tuple(str(item) for item in error.get("loc", ()))
            and error.get("type") == "too_short" for error in exc.errors()
        ) else "INVALID_REQUEST"
        spec = ERRORS[code]
        return JSONResponse(
            status_code=spec.status,
            content={"error": {"code": code, "message": spec.message, "retryable": spec.retryable}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, _exc: Exception):
        spec = ERRORS["INTERNAL_ERROR"]
        return JSONResponse(status_code=spec.status, content={
            "error": {"code": "INTERNAL_ERROR", "message": spec.message, "retryable": spec.retryable},
        })

    @app.get("/api/v1/health")
    def health():
        runtime = app.state.runtime.health()
        agent3 = runtime["agents"]["agent3"]
        agent4 = runtime["agents"]["agent4"]
        configured = agent3["configured"] and agent4["configured"]
        return {
            "status": "ok" if configured else "degraded",
            "service_version": "agent34-service-1.0",
            "contract_version": CONTRACT_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "agent3_version": "Agent3-V5.2.1",
            "agent4_version": "Agent4-V3",
            "agent3_display_name": "证据约束核验智能体",
            "agent4_display_name": "报告生成智能体",
            "agent3_configured": agent3["configured"],
            "agent4_configured": agent4["configured"],
            "agent3_loaded": agent3["loaded"],
            "agent4_loaded": agent4["loaded"],
            "agent3_inference_verified": agent3["inference_verified"],
            "agent4_inference_verified": agent4["inference_verified"],
            "max_concurrency": 1,
            "runtime": runtime,
        }

    @app.get(
        "/api/v1/artifacts/{job_id}/{sample_id}/second_check/{claim_id}/{file_name}",
        dependencies=[Depends(require_bearer)],
    )
    def download_second_check_artifact(
        job_id: str, sample_id: str, claim_id: str, file_name: str,
    ):
        path = resolve_artifact(
            app.state.settings.request_root / "artifacts",
            job_id=job_id, sample_id=sample_id, claim_id=claim_id, file_name=file_name,
        )
        if path is None:
            raise HTTPException(status_code=404, detail={
                "code": "ARTIFACT_NOT_FOUND", "message": "artifact was not found", "retryable": False,
            })
        return FileResponse(path, media_type="image/png", filename=file_name)

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
                raise service_error("SERVICE_BUSY")
            try:
                package = app.state.runtime.agent3().verify_batch(requests)
                app.state.runtime.mark_inference_success("agent3")
            except Exception as exc:
                app.state.runtime.mark_inference_failure("agent3", exc)
                raise _runtime_error(exc) from exc
            finally:
                app.state.runtime.lock.release()
            package = enrich_verified_package(
                package,
                sample_id=parsed.sample_id,
                claim_list=[item.model_dump() for item in parsed.claim_list],
            )
            private_count = persist_private_outputs(
                app.state.settings.request_root,
                job_id=parsed.job_id,
                sample_id=parsed.sample_id,
                payload=package,
            )
            artifacts = persist_second_check_artifacts(
                work,
                app.state.settings.request_root / "artifacts",
                job_id=parsed.job_id,
                sample_id=parsed.sample_id,
            )
            package = public_package(package)
            return {
                "contract_version": CONTRACT_VERSION,
                "pipeline_version": PIPELINE_VERSION,
                "job_id": parsed.job_id,
                "sample_id": parsed.sample_id,
                "agent_code": "agent3",
                "display_name": "证据约束核验智能体",
                "capability": "evidence_verification",
                "source_version": "Agent3-V5.2.1",
                "runtime_version": "agent3-v5.2.1-runtime-3.1",
                "status": "succeeded",
                "check_result": package.get("audit_records", []),
                "private_audit": {
                    "raw_output_retained": private_count > 0,
                    "raw_output_exposed": False,
                },
                "artifacts": artifacts,
                "verified_evidence_package": package,
            }
        finally:
            shutil.rmtree(work, ignore_errors=True)

    @app.post("/api/v1/agent4/report", dependencies=[Depends(require_bearer)])
    def report(payload: ReportPayload):
        from backend.agents.agent4.src.validate_report import validate_report
        if not app.state.runtime.lock.acquire(blocking=False):
            raise service_error("SERVICE_BUSY")
        try:
            platform_report = app.state.runtime.agent4().generate_report(payload.verified_evidence_package)
            app.state.runtime.mark_inference_success("agent4")
        except Exception as exc:
            app.state.runtime.mark_inference_failure("agent4", exc)
            raise _runtime_error(exc) from exc
        finally:
            app.state.runtime.lock.release()
        schema = Path(__file__).resolve().parents[2] / "agents" / "agent4" / "src" / "platform_report_schema_v3.json"
        errors = validate_report(platform_report, schema)
        if errors:
            raise service_error("MODEL_OUTPUT_INVALID")
        markdown_zh = _markdown(platform_report, "zh-CN")
        markdown_en = _markdown(platform_report, "en-US")
        return {
            "contract_version": CONTRACT_VERSION,
            "pipeline_version": PIPELINE_VERSION,
            "job_id": payload.job_id,
            "sample_id": payload.sample_id,
            "agent_code": "agent4",
            "display_name": "报告生成智能体",
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
