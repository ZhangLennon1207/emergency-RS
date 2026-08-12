"""
Reusable in-process Agent4-V3 adapter.

The Qwen2.5-7B base model and LoRA adapter are loaded lazily once and
reused for subsequent report-generation calls in the same process.

This module does not change Agent4 model logic.
"""

from __future__ import annotations

import gc
import threading
from pathlib import Path
from typing import Any

from .slot_runner import Agent4SlotRunner
from .report_runtime import Agent4Runtime


class Agent4Adapter:

    def __init__(
        self,
        *,
        base_model: str,
        adapter_path: str,
        system_prompt_path:
            str | None = None,
    ) -> None:

        self.base_model = str(
            base_model
        )

        self.adapter_path = str(
            adapter_path
        )

        if system_prompt_path:

            self.system_prompt_path = Path(
                system_prompt_path
            )

        else:

            local_prompt = (
                Path(__file__)
                .resolve()
                .parent
                / "system_prompt.txt"
            )

            legacy_prompt = (
                Path(__file__)
                .resolve()
                .parents[1]
                / "system_prompt.txt"
            )

            if local_prompt.is_file():

                self.system_prompt_path = (
                    local_prompt
                )

            elif legacy_prompt.is_file():

                self.system_prompt_path = (
                    legacy_prompt
                )

            else:

                raise FileNotFoundError(
                    "Agent4 system prompt not found"
                )

        self._runner = None
        self._runtime = None
        self._lock = threading.RLock()

    @property
    def loaded(self) -> bool:
        return (
            self._runtime
            is not None
        )

    def _ensure_loaded(
        self,
    ) -> None:

        if self._runtime is not None:
            return

        system_prompt = (
            self.system_prompt_path
            .read_text(
                encoding="utf-8"
            )
        )

        self._runner = (
            Agent4SlotRunner(
                self.base_model,
                self.adapter_path,
                system_prompt,
            )
        )

        self._runtime = (
            Agent4Runtime(
                self._runner
            )
        )

    def health(
        self,
    ) -> dict[str, Any]:

        return {
            "agent":
                "Agent4",

            "version":
                "Agent4-V3",

            "capability":
                "report_generation",

            "loaded":
                self.loaded,
        }

    def generate_report(
        self,
        verified_evidence_package:
            dict[str, Any],
    ) -> dict[str, Any]:

        if not isinstance(
            verified_evidence_package,
            dict
        ):
            raise TypeError(
                "verified_evidence_package "
                "must be a dict"
            )

        with self._lock:

            self._ensure_loaded()

            return self._runtime.build(
                verified_evidence_package
            )

    def close(
        self,
    ) -> None:

        with self._lock:

            self._runtime = None
            self._runner = None

            gc.collect()

            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            except Exception:
                pass
