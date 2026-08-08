"""HTTP client for Wei Songchen's Agent3/4 service."""

from __future__ import annotations

import json
import mimetypes
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
    ) -> dict[str, Any]:
        pre_path = Path(pre_image)
        post_path = Path(post_image)
        for label, path in (("pre_image", pre_path), ("post_image", post_path)):
            if not path.is_file():
                raise FileNotFoundError(f"{label} does not exist")

        def image_part(path: Path) -> tuple[str, Any, str]:
            mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return path.name, path.open("rb"), mime_type

        pre_part = image_part(pre_path)
        post_part = image_part(post_path)
        try:
            response = self._client.post(
                AGENT3_VERIFY_PATH,
                files={
                    "payload": (
                        "payload.json",
                        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "application/json",
                    ),
                    "pre_image": pre_part,
                    "post_image": post_part,
                },
            )
        except httpx.HTTPError as error:
            raise Agent34ServiceError(
                "REMOTE_UNAVAILABLE", "Agent3 service is unavailable"
            ) from error
        finally:
            pre_part[1].close()
            post_part[1].close()
        return self._response_json(response)

    def generate_report(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(AGENT4_REPORT_PATH, json=payload)
        except httpx.HTTPError as error:
            raise Agent34ServiceError(
                "REMOTE_UNAVAILABLE", "Agent4 service is unavailable"
            ) from error
        return self._response_json(response)
