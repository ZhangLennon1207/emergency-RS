from __future__ import annotations

import gc
import importlib
import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from backend.app.artifacts import build_artifact_index, find_result_artifact
from backend.app.clients.agent34 import Agent34Client, Agent34ServiceError
from backend.app.config import Settings
from backend.app.db import JobStore, utc_now
from backend.app.integration import (
    AGENT34_CONTRACT_VERSION,
    AGENT34_PIPELINE_VERSION,
    CLAIM_TYPE_MAPPER_VERSION,
    EVIDENCE_LINKER_VERSION,
    EVIDENCE_MAPPER_VERSION,
    add_claim_types,
    build_agent3_verify_payload,
    build_agent4_report_payload,
    build_evidence_list,
    link_claims_to_evidence,
)


Adapter = Callable[[dict[str, Any], str, dict[str, Any] | None], dict[str, Any]]
Agent34ClientFactory = Callable[[Settings], Any]

ENTRYPOINTS = {
    "agent1": "backend.agents.agent1.adapter:run",
    "agent2": "backend.agents.agent2.adapter:run",
}

OPTIONAL_AGENT3_ARTIFACTS = {
    "damage_map": "damage_instance_color",
    "fused_overlay": "fused_overlay",
    "road_status_map": "road_status_color",
    "building_instance_mask": "building_instance_mask",
}

PRIVATE_REMOTE_KEYS = {
    "images",
    "instruction",
    "prompt",
    "raw_crop_output",
    "raw_first_output",
    "raw_model_output",
    "raw_output",
    "raw_retry_output",
    "second_pass_context",
    "system",
}

DEFAULT_AGENT_SOURCE_VERSIONS = {
    "agent3": "Agent3-V5.2.1",
    "agent4": "Agent4-V3",
}


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _source_version(
    payload: dict[str, Any] | None,
    agent_code: str,
    fallback: str | None = None,
) -> str:
    """Read a remote model/runtime version without depending on one wrapper shape."""

    if isinstance(payload, dict):
        direct_keys = (f"{agent_code}_version", "source_version", "model_version")
        for key in direct_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        agent_metadata = payload.get(agent_code)
        if isinstance(agent_metadata, dict):
            value = agent_metadata.get("version")
            if isinstance(value, str) and value.strip():
                return value.strip()

        versions = payload.get("versions")
        if isinstance(versions, dict):
            value = versions.get(agent_code)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested = value.get("version")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip()

        if agent_code == "agent3":
            package = payload.get("verified_evidence_package")
            if isinstance(package, dict):
                audit_records = package.get("audit_records")
                if isinstance(audit_records, list):
                    for record in audit_records:
                        if not isinstance(record, dict):
                            continue
                        value = record.get("model_version")
                        if isinstance(value, str) and value.strip():
                            return value.strip()

    return fallback or DEFAULT_AGENT_SOURCE_VERSIONS[agent_code]


def _review_summary(
    *,
    agent1_result: dict[str, Any],
    agent1_ok: bool,
    verified_package: dict[str, Any] | None,
    platform_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Keep semantic review requests separate from output-contract failures."""

    agent1_review = bool(
        agent1_ok
        and isinstance(agent1_result.get("review_flags"), dict)
        and agent1_result["review_flags"].get("review_required")
    )

    package = verified_package if isinstance(verified_package, dict) else {}
    pending = package.get("pending_claims")
    pending_items = pending if isinstance(pending, list) else []
    summary = package.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    declared_pending = _nonnegative_int(summary.get("pending"))
    pending_count = max(declared_pending, len(pending_items))

    human_review_claim_count = 0
    model_output_invalid_count = 0
    for claim in pending_items:
        if not isinstance(claim, dict):
            continue
        state = str(claim.get("resolution_state") or "").strip().lower()
        failure_category = str(claim.get("failure_category") or "").strip().lower()
        if state == "model_output_invalid" or failure_category == "format_contract":
            model_output_invalid_count += 1
        elif state == "human_review_required" or claim.get("human_review_required") is True:
            human_review_claim_count += 1

    report = platform_report if isinstance(platform_report, dict) else {}
    review_info = report.get("review_info")
    review_info = review_info if isinstance(review_info, dict) else {}
    explicit_human_present = "human_review_claim_count" in review_info
    explicit_invalid_present = "model_output_invalid_count" in review_info
    explicit_human_count = _nonnegative_int(review_info.get("human_review_claim_count"))
    explicit_invalid_count = _nonnegative_int(review_info.get("model_output_invalid_count"))
    human_review_claim_count = max(human_review_claim_count, explicit_human_count)
    model_output_invalid_count = max(
        model_output_invalid_count, explicit_invalid_count
    )

    classified_pending = human_review_claim_count + model_output_invalid_count
    other_pending_claim_count = max(0, pending_count - classified_pending)

    # Older reports exposed only a Boolean. Use it only when there is no detailed
    # Agent3 pending state that could actually be a format-contract failure.
    report_human_review = bool(review_info.get("human_review_required"))
    if (
        report_human_review
        and not pending_items
        and not explicit_human_present
        and not explicit_invalid_present
        and human_review_claim_count == 0
        and model_output_invalid_count == 0
    ):
        human_review_claim_count = 1

    human_review_required = agent1_review or human_review_claim_count > 0
    attention_required = bool(
        human_review_required
        or model_output_invalid_count > 0
        or other_pending_claim_count > 0
        or review_info.get("attention_required")
    )
    return {
        "attention_required": attention_required,
        "review_required": human_review_required,
        "agent1_review_required": agent1_review,
        "human_review_required": human_review_required,
        "human_review_claim_count": human_review_claim_count,
        "model_output_invalid": model_output_invalid_count > 0,
        "model_output_invalid_count": model_output_invalid_count,
        "pending_claim_count": pending_count,
        "other_pending_claim_count": other_pending_claim_count,
    }


def load_adapter(agent_code: str) -> Adapter:
    entrypoint = ENTRYPOINTS[agent_code]
    module_name, function_name = entrypoint.split(":", maxsplit=1)
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"Adapter entrypoint is not callable: {entrypoint}")
    return function


def create_agent34_client(settings: Settings) -> Agent34Client:
    if not settings.agent34_base_url or not settings.agent34_shared_token:
        raise ValueError("Agent3/4 remote service is not configured")
    return Agent34Client(
        base_url=settings.agent34_base_url,
        shared_token=settings.agent34_shared_token,
        connect_timeout_seconds=settings.agent34_connect_timeout_seconds,
        read_timeout_seconds=settings.agent34_read_timeout_seconds,
    )


def _release_model_memory() -> None:
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is None:
        return
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def _sanitize_remote_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize_remote_value(item)
            for key, item in value.items()
            if key not in PRIVATE_REMOTE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_remote_value(item) for item in value]
    return value


def _artifact_types(result: dict[str, Any]) -> set[str]:
    return {
        str(item.get("artifact_type") or "")
        for item in result.get("artifacts", [])
        if isinstance(item, dict) and item.get("artifact_type")
    }


class JobOrchestrator:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        adapter_loader: Callable[[str], Adapter] = load_adapter,
        agent34_client_factory: Agent34ClientFactory = create_agent34_client,
    ) -> None:
        self.settings = settings
        self.store = store
        self.adapter_loader = adapter_loader
        self.agent34_client_factory = agent34_client_factory
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="emergency-rs-model-queue",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.process_next_job()
            except Exception:
                processed = False
            if not processed:
                self._stop_event.wait(self.settings.queue_poll_seconds)

    def process_next_job(self) -> bool:
        job = self.store.claim_next_job()
        if job is None:
            return False
        self._execute_job(job)
        return True

    @staticmethod
    def _write_error(work_dir: Path, agent_code: str) -> None:
        logs_root = work_dir / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        (logs_root / f"{agent_code}_error.log").write_text(
            traceback.format_exc(), encoding="utf-8"
        )

    def _run_agent(
        self,
        *,
        agent_code: str,
        payload: dict[str, Any],
        work_dir: Path,
        config: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        try:
            adapter = self.adapter_loader(agent_code)
            result = adapter(payload, str(work_dir), config)
            json.dumps(result, ensure_ascii=False)
            return result.get("status") == "succeeded", result
        except Exception as error:
            self._write_error(work_dir, agent_code)
            return False, {
                "agent_code": agent_code,
                "status": "failed",
                "error": f"{agent_code} execution failed",
                "error_type": type(error).__name__,
            }
        finally:
            _release_model_memory()

    def _remote_failure(
        self,
        *,
        agent_code: str,
        work_dir: Path,
        error: Exception,
    ) -> dict[str, Any]:
        self._write_error(work_dir, agent_code)
        result = {
            "agent_code": agent_code,
            "status": "failed",
            "error": f"{agent_code} execution failed",
            "error_type": type(error).__name__,
        }
        if isinstance(error, Agent34ServiceError):
            result["error_code"] = error.code
            result["remote_status_code"] = error.status_code
        return result

    @staticmethod
    def _write_json_artifact(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _prepare_agent3_request(
        self,
        *,
        job_id: str,
        sample_id: str,
        job_root: Path,
        agent1_result: dict[str, Any],
        agent2_result: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Path], list[dict[str, Any]]]:
        ledger_path = find_result_artifact(
            job_root, agent1_result, "evidence_ledger"
        )
        if ledger_path is None:
            raise ValueError("Agent1 evidence ledger artifact is missing")
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        if not isinstance(ledger, dict):
            raise ValueError("Agent1 evidence ledger must contain an object")

        evidence_list = build_evidence_list(
            ledger,
            available_artifact_types=_artifact_types(agent1_result),
        )
        claim_list = add_claim_types(agent2_result.get("claim_list"))
        claim_list = link_claims_to_evidence(claim_list, evidence_list)
        request = build_agent3_verify_payload(
            job_id=job_id,
            sample_id=sample_id,
            evidence_list=evidence_list,
            claim_list=claim_list,
            evidence_schema_version=EVIDENCE_MAPPER_VERSION,
            claim_schema_version=(
                f"1.1+{CLAIM_TYPE_MAPPER_VERSION}+{EVIDENCE_LINKER_VERSION}"
            ),
        )

        optional_assets: dict[str, Path] = {}
        for http_name, artifact_type in OPTIONAL_AGENT3_ARTIFACTS.items():
            path = find_result_artifact(job_root, agent1_result, artifact_type)
            if path is not None:
                optional_assets[http_name] = path
        return request, optional_assets, claim_list

    def _run_agent3(
        self,
        *,
        client: Any,
        job: dict[str, Any],
        job_root: Path,
        agent1_result: dict[str, Any],
        agent2_result: dict[str, Any],
        source_version: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        request, optional_assets, normalized_claims = self._prepare_agent3_request(
            job_id=str(job["job_id"]),
            sample_id=str(job["sample_id"]),
            job_root=job_root,
            agent1_result=agent1_result,
            agent2_result=agent2_result,
        )
        response = client.verify(
            payload=request,
            pre_image=job["pre_image_path"],
            post_image=job["post_image_path"],
            **optional_assets,
        )
        package = response.get("verified_evidence_package")
        if not isinstance(package, dict) or not package:
            raise Agent34ServiceError(
                "REMOTE_RESPONSE_INVALID",
                "Agent3 response is missing verified_evidence_package",
            )

        logs_root = job_root / "logs"
        self._write_json_artifact(logs_root / "agent3_remote_response.json", response)
        sanitized = _sanitize_remote_value(response)
        package = sanitized["verified_evidence_package"]
        artifact_path = job_root / "agent3" / "verified_evidence_package.json"
        self._write_json_artifact(artifact_path, package)
        local_artifacts = [
            {
                "artifact_type": "verified_evidence_package",
                "path": artifact_path.relative_to(job_root).as_posix(),
            }
        ]
        # Remote crop URLs are private service URLs. Copy every permitted crop
        # into the controller-owned Artifact Store so the public job response
        # never exposes the model host, token, or private runtime directory.
        for index, remote_artifact in enumerate(response.get("artifacts", []), start=1):
            if not isinstance(remote_artifact, dict):
                continue
            download_url = remote_artifact.get("download_url")
            claim_id = str(remote_artifact.get("claim_id") or "")
            file_name = str(remote_artifact.get("file_name") or "")
            if not isinstance(download_url, str) or not claim_id or not file_name:
                continue
            destination = job_root / "agent3" / "second_check" / claim_id / file_name
            client.download_artifact(download_url=download_url, destination=destination)
            local_artifacts.append(
                {
                    "artifact_type": f"second_check_crop_{index}",
                    "claim_id": claim_id,
                    "file_name": file_name,
                    "path": destination.relative_to(job_root).as_posix(),
                }
            )
        result = {
            **sanitized,
            "agent_code": "agent3",
            "capability": "evidence_verification",
            "source_version": _source_version(response, "agent3", source_version),
            "status": "succeeded",
            "artifacts": local_artifacts,
        }
        json.dumps(result, ensure_ascii=False)
        return result, normalized_claims

    def _run_agent4(
        self,
        *,
        client: Any,
        job_id: str,
        sample_id: str,
        job_root: Path,
        verified_evidence_package: dict[str, Any],
        source_version: str | None = None,
    ) -> dict[str, Any]:
        request = build_agent4_report_payload(
            job_id=job_id,
            sample_id=sample_id,
            verified_evidence_package=verified_evidence_package,
        )
        response = client.generate_report(payload=request)
        platform_report = response.get("platform_report_json")
        markdown_zh = response.get("markdown_report_zh")
        markdown_en = response.get("markdown_report_en")
        if not isinstance(platform_report, dict) or not platform_report:
            raise Agent34ServiceError(
                "REMOTE_RESPONSE_INVALID",
                "Agent4 response is missing platform_report_json",
            )
        if not isinstance(markdown_zh, str) or not isinstance(markdown_en, str):
            raise Agent34ServiceError(
                "REMOTE_RESPONSE_INVALID",
                "Agent4 response is missing bilingual Markdown",
            )

        sanitized = _sanitize_remote_value(response)
        agent4_root = job_root / "agent4"
        report_path = agent4_root / "platform_report.json"
        zh_path = agent4_root / "report_zh.md"
        en_path = agent4_root / "report_en.md"
        self._write_json_artifact(report_path, sanitized["platform_report_json"])
        zh_path.write_text(markdown_zh, encoding="utf-8")
        en_path.write_text(markdown_en, encoding="utf-8")
        result = {
            **sanitized,
            "agent_code": "agent4",
            "capability": "report_generation",
            "source_version": _source_version(response, "agent4", source_version),
            "status": "succeeded",
            "artifacts": [
                {
                    "artifact_type": "platform_report",
                    "path": report_path.relative_to(job_root).as_posix(),
                },
                {
                    "artifact_type": "markdown_report_zh",
                    "path": zh_path.relative_to(job_root).as_posix(),
                },
                {
                    "artifact_type": "markdown_report_en",
                    "path": en_path.relative_to(job_root).as_posix(),
                },
            ],
        }
        json.dumps(result, ensure_ascii=False)
        return result

    def _execute_job(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])
        sample_id = str(job["sample_id"])
        job_root = self.settings.runtime_root / "jobs" / job_id
        payload = {
            "sample_id": sample_id,
            "pre_image": job["pre_image_path"],
            "post_image": job["post_image_path"],
        }
        errors: list[dict[str, str]] = []

        self.store.update_job(
            job_id,
            status="running_agent1",
            stage="Agent1 正在提取视觉证据",
            progress=10,
        )
        agent1_ok, agent1_result = self._run_agent(
            agent_code="agent1",
            payload=payload,
            work_dir=job_root,
            config=self.settings.agent1_config,
        )
        if not agent1_ok:
            errors.append(
                {"agent": "agent1", "message": str(agent1_result.get("error"))}
            )

        self.store.update_job(
            job_id,
            status="running_agent2",
            stage="Agent2 正在生成变化描述",
            progress=45,
            errors_json=errors,
        )
        # Agent2 remains independent from Agent1 and sees only the image pair.
        agent2_ok, agent2_result = self._run_agent(
            agent_code="agent2",
            payload=dict(payload),
            work_dir=job_root,
            config=self.settings.agent2_config,
        )
        if not agent2_ok:
            errors.append(
                {"agent": "agent2", "message": str(agent2_result.get("error"))}
            )

        remote_configured = self.settings.agent34_configured
        agent3_ok: bool | None = None
        agent4_ok: bool | None = None
        agent3_result: dict[str, Any] = {}
        agent4_result: dict[str, Any] = {}
        remote_versions: dict[str, str] = {}
        remote_skip_reason = "Agent3/4 远程服务尚未配置"

        if remote_configured and agent1_ok and agent2_ok:
            client = None
            try:
                client = self.agent34_client_factory(self.settings)
                if hasattr(client, "health"):
                    try:
                        remote_health = client.health()
                    except Exception:
                        remote_health = None
                    if isinstance(remote_health, dict):
                        remote_versions = {
                            code: _source_version(remote_health, code)
                            for code in ("agent3", "agent4")
                        }
                self.store.update_job(
                    job_id,
                    status="running_agent3",
                    stage="Agent3 正在逐条核验证据",
                    progress=65,
                    errors_json=errors,
                )
                try:
                    agent3_result, normalized_claims = self._run_agent3(
                        client=client,
                        job=job,
                        job_root=job_root,
                        agent1_result=agent1_result,
                        agent2_result=agent2_result,
                        source_version=remote_versions.get("agent3"),
                    )
                    agent2_result = dict(agent2_result)
                    agent2_result["claim_list"] = normalized_claims
                    agent2_result["claim_type_mapper_version"] = (
                        CLAIM_TYPE_MAPPER_VERSION
                    )
                    agent2_result["evidence_linker_version"] = EVIDENCE_LINKER_VERSION
                    agent3_ok = True
                except Exception as error:
                    agent3_ok = False
                    agent3_result = self._remote_failure(
                        agent_code="agent3", work_dir=job_root, error=error
                    )
                    errors.append(
                        {"agent": "agent3", "message": agent3_result["error"]}
                    )

                if agent3_ok:
                    self.store.update_job(
                        job_id,
                        status="running_agent4",
                        stage="Agent4 正在生成可信双语报告",
                        progress=85,
                        errors_json=errors,
                    )
                    try:
                        agent4_result = self._run_agent4(
                            client=client,
                            job_id=job_id,
                            sample_id=sample_id,
                            job_root=job_root,
                            verified_evidence_package=agent3_result[
                                "verified_evidence_package"
                            ],
                            source_version=remote_versions.get("agent4"),
                        )
                        agent4_ok = True
                    except Exception as error:
                        agent4_ok = False
                        agent4_result = self._remote_failure(
                            agent_code="agent4", work_dir=job_root, error=error
                        )
                        errors.append(
                            {"agent": "agent4", "message": agent4_result["error"]}
                        )
                else:
                    remote_skip_reason = "Agent3 失败，Agent4 未执行"
            except Exception as error:
                agent3_ok = False
                agent3_result = self._remote_failure(
                    agent_code="agent3", work_dir=job_root, error=error
                )
                errors.append({"agent": "agent3", "message": agent3_result["error"]})
                remote_skip_reason = "Agent3/4 远程服务客户端创建失败"
            finally:
                if client is not None and hasattr(client, "close"):
                    try:
                        client.close()
                    except Exception:
                        logs_root = job_root / "logs"
                        logs_root.mkdir(parents=True, exist_ok=True)
                        (logs_root / "agent34_client_close_error.log").write_text(
                            traceback.format_exc(), encoding="utf-8"
                        )
        elif remote_configured:
            remote_skip_reason = "Agent1 或 Agent2 失败，Agent3/4 未执行"

        self.store.update_job(
            job_id,
            status="assembling",
            stage="正在整理统一结果",
            progress=95,
            errors_json=errors,
        )
        successful_results = {
            code: result
            for code, ok, result in (
                ("agent1", agent1_ok, agent1_result),
                ("agent2", agent2_ok, agent2_result),
                ("agent3", agent3_ok, agent3_result),
                ("agent4", agent4_ok, agent4_result),
            )
            if ok
        }
        artifacts = build_artifact_index(job_root, job_id, successful_results)
        result = self._build_result(
            job_id=job_id,
            sample_id=sample_id,
            agent1_ok=agent1_ok,
            agent1_result=agent1_result,
            agent2_ok=agent2_ok,
            agent2_result=agent2_result,
            agent3_ok=agent3_ok,
            agent3_result=agent3_result,
            agent4_ok=agent4_ok,
            agent4_result=agent4_result,
            remote_configured=remote_configured,
            remote_skip_reason=remote_skip_reason,
            artifacts=artifacts,
        )

        if agent1_ok and agent2_ok and not remote_configured:
            status, stage = "succeeded", "Agent1/2 本地分析完成"
        elif all(outcome is True for outcome in (agent1_ok, agent2_ok, agent3_ok, agent4_ok)):
            status = "succeeded"
            if result["review_required"]:
                stage = "四智能体分析完成，存在待人工复核项"
            elif result["attention_required"]:
                stage = "四智能体分析完成，存在待处理项"
            else:
                stage = "四智能体分析与报告生成完成"
        elif any(outcome is True for outcome in (agent1_ok, agent2_ok, agent3_ok, agent4_ok)):
            status, stage = "partial_success", "部分智能体完成，已保留可用结果"
        else:
            status, stage = "failed", "分析失败"
        self.store.update_job(
            job_id,
            status=status,
            stage=stage,
            progress=100,
            completed_at=utc_now(),
            result_json=result,
            errors_json=errors,
        )

    def _build_result(
        self,
        *,
        job_id: str,
        sample_id: str,
        agent1_ok: bool,
        agent1_result: dict[str, Any],
        agent2_ok: bool,
        agent2_result: dict[str, Any],
        agent3_ok: bool | None,
        agent3_result: dict[str, Any],
        agent4_ok: bool | None,
        agent4_result: dict[str, Any],
        remote_configured: bool,
        remote_skip_reason: str,
        artifacts: dict[str, str],
    ) -> dict[str, Any]:
        agent4_skip_reason = (
            "Agent3 失败，Agent4 未执行"
            if agent3_ok is False
            else remote_skip_reason
        )
        runs = [
            self._agent_run("agent1", "visual_evidence", agent1_ok, agent1_result),
            self._agent_run("agent2", "change_description", agent2_ok, agent2_result),
            self._remote_run(
                "agent3",
                "evidence_verification",
                agent3_ok,
                agent3_result,
                remote_skip_reason,
            ),
            self._remote_run(
                "agent4",
                "report_generation",
                agent4_ok,
                agent4_result,
                agent4_skip_reason,
            ),
        ]

        verified_package = (
            agent3_result.get("verified_evidence_package") if agent3_ok else None
        )
        platform_report = (
            agent4_result.get("platform_report_json") if agent4_ok else None
        )
        review_summary = _review_summary(
            agent1_result=agent1_result,
            agent1_ok=agent1_ok,
            verified_package=verified_package,
            platform_report=platform_report,
        )

        four_agent_complete = all(
            outcome is True for outcome in (agent1_ok, agent2_ok, agent3_ok, agent4_ok)
        )
        return {
            "contract_version": self.settings.contract_version,
            "pipeline_version": (
                AGENT34_PIPELINE_VERSION
                if remote_configured
                else self.settings.pipeline_version
            ),
            "agent34_contract_version": (
                AGENT34_CONTRACT_VERSION if remote_configured else None
            ),
            "job_id": job_id,
            "sample_id": sample_id,
            "scope": (
                "four_agent_remote_service"
                if remote_configured
                else "agent1_agent2_local_only"
            ),
            "four_agent_pipeline_complete": four_agent_complete,
            # review_required is retained for existing clients, but now means
            # semantic/manual review only. Use attention_required for any issue.
            "review_required": review_summary["review_required"],
            "attention_required": review_summary["attention_required"],
            "review_summary": review_summary,
            "artifacts": artifacts,
            "agent_runs": runs,
            "agent1": {
                "status": "succeeded" if agent1_ok else "failed",
                "source_schema_versions": (
                    agent1_result.get("source_schema_versions") if agent1_ok else None
                ),
                "summary": agent1_result.get("summary") if agent1_ok else None,
                "review_flags": (
                    agent1_result.get("review_flags") if agent1_ok else None
                ),
            },
            "agent2": {
                "status": "succeeded" if agent2_ok else "failed",
                "source_schema_version": (
                    agent2_result.get("source_schema_version") if agent2_ok else None
                ),
                "description": agent2_result.get("description") if agent2_ok else None,
                "language": agent2_result.get("language", "en") if agent2_ok else None,
                "claim_builder_version": (
                    agent2_result.get("claim_builder_version") if agent2_ok else None
                ),
                "claim_type_mapper_version": (
                    agent2_result.get("claim_type_mapper_version") if agent2_ok else None
                ),
                "evidence_linker_version": (
                    agent2_result.get("evidence_linker_version") if agent2_ok else None
                ),
                "claim_list": (
                    agent2_result.get("claim_list") if agent2_ok else None
                ),
                "verified": bool(agent3_ok),
                "verification_status": "verified" if agent3_ok else "unverified",
                "notice": (
                    "Agent2 claims have been checked by Agent3."
                    if agent3_ok
                    else agent2_result.get("notice")
                    or "模型生成的变化描述，尚未经过 Agent3 证据校验。"
                ),
            },
            "agent3": (
                agent3_result
                if agent3_ok is not None
                else {"status": "skipped", "result": None, "reason": remote_skip_reason}
            ),
            "agent4": (
                agent4_result
                if agent4_ok is not None
                else {"status": "skipped", "result": None, "reason": agent4_skip_reason}
            ),
            "verification": agent3_result if agent3_ok else None,
            "report": agent4_result if agent4_ok else None,
        }

    @staticmethod
    def _agent_run(
        agent_code: str,
        capability: str,
        succeeded: bool,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "agent_run_id": f"run_{agent_code}",
            "agent_code": agent_code,
            "capability": capability,
            "status": "succeeded" if succeeded else "failed",
            "progress": 100,
            "error": None if succeeded else {"message": result.get("error")},
        }

    @staticmethod
    def _remote_run(
        agent_code: str,
        capability: str,
        outcome: bool | None,
        result: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        if outcome is None:
            return {
                "agent_run_id": f"run_{agent_code}",
                "agent_code": agent_code,
                "capability": capability,
                "status": "skipped",
                "progress": 0,
                "error": None,
                "reason": reason,
            }
        return {
            "agent_run_id": f"run_{agent_code}",
            "agent_code": agent_code,
            "capability": capability,
            "status": "succeeded" if outcome else "failed",
            "progress": 100,
            "error": None if outcome else {"message": result.get("error")},
        }

    def health(self) -> dict[str, Any]:
        capabilities = self.settings.capability_status()
        local_ready = all(
            capabilities[code]["configured"] for code in ("agent1", "agent2")
        )
        remote_ready = all(
            capabilities[code]["configured"] for code in ("agent3", "agent4")
        )
        return {
            "status": "ok" if local_ready else "degraded",
            "pipeline_scope": (
                "four_agent_remote_service"
                if remote_ready
                else "agent1_agent2_local_only"
            ),
            "four_agent_pipeline_configured": local_ready and remote_ready,
            "four_agent_pipeline_complete": False,
            "capabilities": capabilities,
            "queue_worker_running": bool(self._thread and self._thread.is_alive()),
        }
