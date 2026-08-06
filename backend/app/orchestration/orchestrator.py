from __future__ import annotations

import gc
import importlib
import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from backend.app.artifacts import build_artifact_index
from backend.app.config import Settings
from backend.app.db import JobStore, utc_now


Adapter = Callable[[dict[str, Any], str, dict[str, Any] | None], dict[str, Any]]
ENTRYPOINTS = {
    "agent1": "backend.agents.agent1.adapter:run",
    "agent2": "backend.agents.agent2.adapter:run",
}


def load_adapter(agent_code: str) -> Adapter:
    entrypoint = ENTRYPOINTS[agent_code]
    module_name, function_name = entrypoint.split(":", maxsplit=1)
    function = getattr(importlib.import_module(module_name), function_name)
    if not callable(function):
        raise TypeError(f"Adapter entrypoint is not callable: {entrypoint}")
    return function


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


class JobOrchestrator:
    def __init__(
        self,
        settings: Settings,
        store: JobStore,
        adapter_loader: Callable[[str], Adapter] = load_adapter,
    ) -> None:
        self.settings = settings
        self.store = store
        self.adapter_loader = adapter_loader
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="emergency-rs-local-model-queue",
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
            logs_root = work_dir / "logs"
            logs_root.mkdir(parents=True, exist_ok=True)
            (logs_root / f"{agent_code}_error.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            return False, {
                "agent_code": agent_code,
                "status": "failed",
                # Full exception details remain in the ignored runtime log.
                # Public API errors must not expose model/input absolute paths.
                "error": f"{agent_code} execution failed",
                "error_type": type(error).__name__,
            }
        finally:
            _release_model_memory()

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
            progress=55,
            errors_json=errors,
        )
        agent2_payload = {**payload, "visual_evidence": agent1_result if agent1_ok else None}
        agent2_ok, agent2_result = self._run_agent(
            agent_code="agent2",
            payload=agent2_payload,
            work_dir=job_root,
            config=self.settings.agent2_config,
        )
        if not agent2_ok:
            errors.append(
                {"agent": "agent2", "message": str(agent2_result.get("error"))}
            )

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
            )
            if ok
        }
        artifacts = build_artifact_index(job_root, job_id, successful_results)
        result = self._build_result(
            job_id=job_id,
            agent1_ok=agent1_ok,
            agent1_result=agent1_result,
            agent2_ok=agent2_ok,
            agent2_result=agent2_result,
            artifacts=artifacts,
        )
        success_count = int(agent1_ok) + int(agent2_ok)
        if success_count == 2:
            status, stage = "succeeded", "Agent1/2 本地分析完成"
        elif success_count == 1:
            status, stage = "partial_success", "Agent1/2 部分分析完成"
        else:
            status, stage = "failed", "Agent1/2 分析失败"
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
        agent1_ok: bool,
        agent1_result: dict[str, Any],
        agent2_ok: bool,
        agent2_result: dict[str, Any],
        artifacts: dict[str, str],
    ) -> dict[str, Any]:
        skipped_reason = "真实 Agent3/4 adapter 或远程服务尚未接入"
        runs = [
            self._agent_run("agent1", "visual_evidence", agent1_ok, agent1_result),
            self._agent_run("agent2", "change_description", agent2_ok, agent2_result),
            self._skipped_run("agent3", "evidence_verification", skipped_reason),
            self._skipped_run("agent4", "report_generation", skipped_reason),
        ]
        return {
            "contract_version": self.settings.contract_version,
            "pipeline_version": self.settings.pipeline_version,
            "job_id": job_id,
            "scope": "agent1_agent2_local_only",
            "four_agent_pipeline_complete": False,
            "artifacts": artifacts,
            "agent_runs": runs,
            "agent1": {
                "status": "succeeded" if agent1_ok else "failed",
                "summary": agent1_result.get("summary") if agent1_ok else None,
            },
            "agent2": {
                "status": "succeeded" if agent2_ok else "failed",
                "description": agent2_result.get("description") if agent2_ok else None,
                "language": "en",
                "verified": False,
                "verification_status": "unverified",
                "notice": "模型生成的变化描述，尚未经过 Agent3 证据校验。",
            },
            "agent3": {"status": "skipped", "result": None, "reason": skipped_reason},
            "agent4": {"status": "skipped", "result": None, "reason": skipped_reason},
            "verification": None,
            "report": None,
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
    def _skipped_run(agent_code: str, capability: str, reason: str) -> dict[str, Any]:
        return {
            "agent_run_id": f"run_{agent_code}",
            "agent_code": agent_code,
            "capability": capability,
            "status": "skipped",
            "progress": 0,
            "error": None,
            "reason": reason,
        }

    def health(self) -> dict[str, Any]:
        capabilities = self.settings.capability_status()
        local_ready = all(capabilities[code]["configured"] for code in ("agent1", "agent2"))
        return {
            "status": "ok" if local_ready else "degraded",
            "pipeline_scope": "agent1_agent2_local_only",
            "four_agent_pipeline_complete": False,
            "capabilities": capabilities,
            "queue_worker_running": bool(self._thread and self._thread.is_alive()),
        }
