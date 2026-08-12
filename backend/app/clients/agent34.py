"""HTTP client for Wei Songchen's Agent3/4 service."""

from __future__ import annotations

import json
import mimetypes
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import httpx

from backend.app.integration.agent34_contract import (
    AGENT3_VERIFY_PATH,
    AGENT4_REPORT_PATH,
)


class Agent34ServiceError(RuntimeError):
    """A sanitized remote-service failure safe for orchestration logs."""

    def __init__(self, code: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class Agent34Client:
    def __init__(
        self,
        *,
        base_url: str,
        shared_token: str,
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 900.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("Agent3/4 base_url must use http or https")
        if not shared_token.strip():
            raise ValueError("Agent3/4 shared token must not be empty")
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {shared_token}"},
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Agent34Client":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as error:
            raise Agent34ServiceError(
                "REMOTE_RESPONSE_INVALID",
                "Agent3/4 service returned non-JSON content",
                response.status_code,
            ) from error
        if not isinstance(payload, dict):
            raise Agent34ServiceError(
                "REMOTE_RESPONSE_INVALID",
                "Agent3/4 service returned a non-object JSON response",
                response.status_code,
            )
        if response.is_error:
            error_payload = (
                payload.get("error") if isinstance(payload.get("error"), dict) else {}
            )
            code = str(error_payload.get("code") or "REMOTE_REQUEST_FAILED")
            raise Agent34ServiceError(
                code,
                f"Agent3/4 service request failed ({code})",
                response.status_code,
            )
        return payload

    def health(self) -> dict[str, Any]:
        try:
            response = self._client.get("/api/v1/health")
        except httpx.HTTPError as error:
            raise Agent34ServiceError(
                "REMOTE_UNAVAILABLE", "Agent3/4 service is unavailable"
            ) from error
        return self._response_json(response)

    def verify(
        self,
        *,
        payload: dict[str, Any],
        pre_image: str | Path,
        post_image: str | Path,
        damage_map: str | Path | None = None,
        fused_overlay: str | Path | None = None,
        road_status_map: str | Path | None = None,
        building_instance_mask: str | Path | None = None,
    ) -> dict[str, Any]:
        supplied: dict[str, str | Path | None] = {
            "pre_image": pre_image,
            "post_image": post_image,
            "damage_map": damage_map,
            "fused_overlay": fused_overlay,
            "road_status_map": road_status_map,
            "building_instance_mask": building_instance_mask,
        }
        paths: dict[str, Path] = {}
        for label, value in supplied.items():
            if value is None:
                continue
            path = Path(value)
            if not path.is_file():
                raise FileNotFoundError(f"{label} does not exist")
            paths[label] = path
        for required in ("pre_image", "post_image"):
            if required not in paths:
                raise ValueError(f"{required} is required")

        with ExitStack() as stack:
            files: dict[str, tuple[str, Any, str]] = {}
            for label, path in paths.items():
                mime_type = (
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                )
                files[label] = (
                    path.name,
                    stack.enter_context(path.open("rb")),
                    mime_type,
                )
            try:
                response = self._client.post(
                    AGENT3_VERIFY_PATH,
                    data={"payload": json.dumps(payload, ensure_ascii=False)},
                    files=files,
                )
            except httpx.HTTPError as error:
                raise Agent34ServiceError(
                    "REMOTE_UNAVAILABLE", "Agent3 service is unavailable"
                ) from error
        return self._response_json(response)

    def generate_report(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(AGENT4_REPORT_PATH, json=payload)
        except httpx.HTTPError as error:
            raise Agent34ServiceError(
                "REMOTE_UNAVAILABLE", "Agent4 service is unavailable"
            ) from error
        return self._response_json(response)

    def download_artifact(self, *, download_url: str, destination: str | Path) -> Path:
        """Download a protected Agent34 artifact into the controller store."""
        if not download_url.startswith("/api/v1/artifacts/") or ".." in download_url:
            raise Agent34ServiceError("REMOTE_ARTIFACT_INVALID", "Agent34 artifact URL is invalid")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", download_url) as response:
                if response.is_error:
                    self._response_json(response)
                with target.open("wb") as stream:
                    for chunk in response.iter_bytes():
                        stream.write(chunk)
        except httpx.HTTPError as error:
            target.unlink(missing_ok=True)
            raise Agent34ServiceError("REMOTE_UNAVAILABLE", "Agent34 artifact download failed") from error
        return target
