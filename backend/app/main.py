from __future__ import annotations

import io
import mimetypes
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from backend.app.artifacts import build_artifact_index, resolve_artifact
from backend.app.config import Settings
from backend.app.db import JobStore
from backend.app.orchestration import JobOrchestrator


ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg"}
ALLOWED_FORMATS = {"PNG", "JPEG"}
SAMPLE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    if upload.content_type not in ALLOWED_CONTENT_TYPES:
        raise api_error(415, "INVALID_IMAGE_TYPE", "仅支持 PNG 或 JPEG 图片")
    data = bytearray()
    while chunk := await upload.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > max_bytes:
            raise api_error(413, "IMAGE_TOO_LARGE", "上传图片超过大小限制")
    return bytes(data)


def _decode_image(data: bytes, *, max_pixels: int) -> Image.Image:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ALLOWED_FORMATS:
                raise api_error(415, "INVALID_IMAGE_TYPE", "仅支持 PNG 或 JPEG 图片")
            width, height = source.size
            if width <= 0 or height <= 0:
                raise ValueError("empty image dimensions")
            if width * height > max_pixels:
                raise api_error(413, "IMAGE_TOO_LARGE", "图片像素数量超过限制")
            source.load()
            return ImageOps.exif_transpose(source).convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise api_error(422, "IMAGE_DECODE_FAILED", "无法解码为有效图片") from error


def _public_job(job: dict[str, Any], settings: Settings) -> dict[str, Any]:
    return {
        "job_id": job["job_id"],
        "sample_id": job["sample_id"],
        "contract_version": settings.contract_version,
        "pipeline_version": settings.pipeline_version,
        "status": job["status"],
        "stage": job["stage"],
        "progress": job["progress"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "result": job["result"],
        "errors": job["errors"],
    }


def create_app(settings: Settings | None = None, *, start_worker: bool = True) -> FastAPI:
    current_settings = settings or Settings.from_env()
    store = JobStore(current_settings.database_path)
    orchestrator = JobOrchestrator(current_settings, store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        current_settings.ensure_runtime()
        store.initialize()
        store.recover_incomplete()
        if start_worker:
            orchestrator.start()
        yield
        orchestrator.stop()

    app = FastAPI(
        title="Emergency RS Agent1/2 Integration API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = current_settings
    app.state.store = store
    app.state.orchestrator = orchestrator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(current_settings.frontend_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.get("/")
    def service_info() -> dict[str, Any]:
        return {
            "service": "Emergency RS Agent1/2 Integration API",
            "docs": "/docs",
            "health": "/api/v1/health",
            "pipeline_scope": "agent1_agent2_local_only",
            "four_agent_pipeline_complete": False,
        }

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return orchestrator.health()

    @app.post("/api/v1/jobs", status_code=202)
    async def create_job(
        pre_image: UploadFile = File(...),
        post_image: UploadFile = File(...),
        sample_id: str | None = Form(default=None),
    ) -> JSONResponse:
        pre_data = await _read_upload(pre_image, current_settings.max_upload_bytes)
        post_data = await _read_upload(post_image, current_settings.max_upload_bytes)
        pre = _decode_image(pre_data, max_pixels=current_settings.max_image_pixels)
        post = _decode_image(post_data, max_pixels=current_settings.max_image_pixels)
        if pre.size != post.size:
            raise api_error(
                422,
                "IMAGE_SIZE_MISMATCH",
                f"灾前图与灾后图尺寸不一致：{pre.size} 与 {post.size}",
            )

        job_id = uuid.uuid4().hex
        selected_sample_id = (sample_id or job_id).strip()
        if not SAMPLE_ID_PATTERN.fullmatch(selected_sample_id):
            raise api_error(422, "INVALID_SAMPLE_ID", "sample_id 格式无效")
        job_root = current_settings.runtime_root / "jobs" / job_id
        input_root = job_root / "inputs"
        input_root.mkdir(parents=True, exist_ok=False)
        pre_path = input_root / "pre.png"
        post_path = input_root / "post.png"
        pre.save(pre_path, format="PNG")
        post.save(post_path, format="PNG")
        build_artifact_index(job_root, job_id, {})

        job = store.create_job(
            job_id=job_id,
            sample_id=selected_sample_id,
            pre_image_path=pre_path,
            post_image_path=post_path,
            pre_original_name=pre_image.filename or "pre_image",
            post_original_name=post_image.filename or "post_image",
        )
        body = _public_job(job, current_settings)
        body["status_url"] = f"/api/v1/jobs/{job_id}"
        return JSONResponse(status_code=202, content=body)

    @app.get("/api/v1/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        job = store.get_job(job_id)
        if job is None:
            raise api_error(404, "JOB_NOT_FOUND", "任务不存在")
        return _public_job(job, current_settings)

    @app.get("/api/v1/jobs/{job_id}/result")
    def get_result(job_id: str) -> dict[str, Any]:
        job = store.get_job(job_id)
        if job is None:
            raise api_error(404, "JOB_NOT_FOUND", "任务不存在")
        if job["result"] is None:
            raise api_error(409, "RESULT_NOT_READY", "任务结果尚未生成")
        return job["result"]

    @app.get("/api/v1/jobs/{job_id}/artifacts/{artifact_key}")
    def get_artifact(job_id: str, artifact_key: str) -> FileResponse:
        if store.get_job(job_id) is None:
            raise api_error(404, "JOB_NOT_FOUND", "任务不存在")
        job_root = current_settings.runtime_root / "jobs" / job_id
        path = resolve_artifact(job_root, artifact_key)
        if path is None:
            raise api_error(404, "ARTIFACT_NOT_FOUND", "结果文件不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    return app


app = create_app()
