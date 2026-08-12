from __future__ import annotations

import gc
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MockAgent3:
    def verify_batch(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        accepted = []
        for request in requests:
            inp = request["input"]
            accepted.append({
                "scene_uid": inp["scene_uid"], "claim_id": inp["claim_id"],
                "claim_type": inp["claim_type"], "support_status": "supported",
                "evidence_ids": [x["evidence_id"] for x in inp["structured_evidence"]],
                "reason": "mock verification", "suggested_revision": "",
            })
        return {"schema_version": "agent3_verified_package_v1", "accepted_claims": accepted,
                "revised_claims": [], "rejected_claims": [], "pending_claims": [],
                "audit_records": [], "summary": {"accepted": len(accepted), "revised": 0, "rejected": 0, "pending": 0}}


class MockAgent4:
    def generate_report(self, package: dict[str, Any]) -> dict[str, Any]:
        counts = package.get("summary", {})
        return {"schema_version": "agent4_report_v3",
                "report_type": "preliminary_remote_sensing_assessment",
                "task_info": package.get("task_info", {}),
                "report_summary": {"accepted_count": counts.get("accepted", 0),
                                   "revised_count": counts.get("revised", 0),
                                   "rejected_count": counts.get("rejected", 0),
                                   "pending_count": counts.get("pending", 0)},
                "sections": {"executive_summary": {"zh-CN": "模拟报告摘要", "en-US": "Mock report summary"},
                "key_disaster_indicators": [], "regional_assessment": [],
                "evidence_support_and_consistency_check": [], "limitations_and_nonconclusive_items": []},
                "evidence_index": [],
                "review_info": {
                    "report_review_state": "unreviewed",
                    "human_review_required": False,
                    "human_review_claim_count": 0,
                    "attention_required": False,
                    "invalid_model_output_count": 0,
                },
                "disclaimer": {"zh-CN": "本报告不替代现场核查或权威结论。",
                               "en-US": "This report does not replace field verification."}}


class RuntimeManager:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.active_agent: str | None = None
        self._agent3 = None
        self._agent4 = None
        self._inference_verified = {"agent3": False, "agent4": False}
        self._last_success_at = {"agent3": None, "agent4": None}
        self._last_error = {"agent3": None, "agent4": None}

    def _configured(self, agent: str) -> bool:
        if self.settings.runtime_mode == "mock":
            return True
        paths = (
            (self.settings.agent3_base_model, self.settings.agent3_adapter)
            if agent == "agent3"
            else (self.settings.agent4_base_model, self.settings.agent4_adapter)
        )
        return all(value and Path(value).exists() for value in paths)

    def mark_inference_success(self, agent: str) -> None:
        self._inference_verified[agent] = True
        self._last_success_at[agent] = datetime.now(timezone.utc).isoformat()
        self._last_error[agent] = None

    def mark_inference_failure(self, agent: str, exc: Exception) -> None:
        self._last_error[agent] = type(exc).__name__

    def _release(self):
        self._agent3 = None
        if self._agent4 is not None and hasattr(self._agent4, "close"):
            self._agent4.close()
        self._agent4 = None
        self.active_agent = None
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def agent3(self):
        if self.active_agent != "agent3":
            self._release()
        if self._agent3 is None:
            if self.settings.runtime_mode == "mock":
                self._agent3 = MockAgent3()
            else:
                from backend.agents.agent3.adapter import Agent3Adapter
                self._agent3 = Agent3Adapter()
            self.active_agent = "agent3"
        return self._agent3

    def agent4(self):
        if self.active_agent != "agent4":
            self._release()
        if self._agent4 is None:
            if self.settings.runtime_mode == "mock":
                self._agent4 = MockAgent4()
            else:
                from backend.agents.agent4.src.reusable_adapter import Agent4Adapter
                self._agent4 = Agent4Adapter(base_model=self.settings.agent4_base_model,
                                             adapter_path=self.settings.agent4_adapter)
            self.active_agent = "agent4"
        return self._agent4

    def health(self):
        agents = {}
        for name, runtime in (("agent3", self._agent3), ("agent4", self._agent4)):
            agents[name] = {
                "configured": self._configured(name),
                "loaded": runtime is not None,
                "inference_verified": self._inference_verified[name],
                "last_success_at": self._last_success_at[name],
                "last_error": self._last_error[name],
            }
        return {
            "mode": self.settings.runtime_mode,
            "active_agent": self.active_agent,
            "busy": self.lock._is_owned(),
            "agents": agents,
        }
