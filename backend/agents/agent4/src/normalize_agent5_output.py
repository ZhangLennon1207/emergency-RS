#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import argparse
from pathlib import Path

REQUIRED_HEADERS = [
    "## 1. 报告摘要",
    "## 2. 核心灾情指标",
    "## 3. 分区评估结果",
    "## 4. 证据支撑与一致性校验",
    "## 5. 证据局限与不可下结论事项"
]

def parse_json_loose(text):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("无法解析模型输出为 JSON")


def get_task_id(platform, outer_task_id=""):
    return (
        outer_task_id
        or platform.get("task_id", "")
        or platform.get("data_basis", {}).get("task_id", "")
    )


def get_key_findings(platform):
    if "key_findings" in platform:
        return platform.get("key_findings", [])

    findings = []
    for x in platform.get("accepted_claims", []):
        findings.append({
            "claim_id": x.get("claim_id", ""),
            "finding": x.get("claim", ""),
            "evidence_ids": x.get("evidence_ids", [])
        })
    return findings


def get_qualified_findings(platform):
    if "qualified_findings" in platform:
        return platform.get("qualified_findings", [])

    findings = []
    for x in platform.get("qualified_claims", []):
        findings.append({
            "claim_id": x.get("claim_id", ""),
            "finding": x.get("safe_claim") or x.get("claim", ""),
            "evidence_ids": x.get("evidence_ids", []),
            "reason": x.get("reason", "")
        })
    return findings


def get_excluded_claims(platform):
    if "excluded_claims" in platform:
        return platform.get("excluded_claims", [])
    return platform.get("rejected_claims", [])


def get_source_evidence_ids(platform):
    if "source_evidence_ids" in platform:
        return platform.get("source_evidence_ids", [])
    return platform.get("data_basis", {}).get("source_evidence_ids", [])


def rebuild_markdown_from_platform(platform, outer_task_id=""):
    task_id = get_task_id(platform, outer_task_id)
    overall_status = platform.get("overall_status", "warning")
    key_findings = get_key_findings(platform)
    qualified_findings = get_qualified_findings(platform)
    excluded_claims = get_excluded_claims(platform)
    source_evidence_ids = get_source_evidence_ids(platform)
    limitations = platform.get("limitations", [])

    lines = []
    lines.append("# 遥感灾情评估报告")
    lines.append("")
    lines.append("## 1. 报告摘要")
    lines.append(f"- 任务编号：`{task_id}`。")
    lines.append(f"- 当前报告状态：`{overall_status}`。")
    lines.append("- 本报告仅基于 Agent4 证据校验后的可信结果生成，未通过证据校验的内容不进入正式灾情结论。")
    lines.append("")

    lines.append("## 2. 核心灾情指标")
    if key_findings:
        for item in key_findings:
            finding = item.get("finding") or "该条结论已通过证据校验。"
            eids = ", ".join(item.get("evidence_ids", [])) or "未列出"
            lines.append(f"- {finding}（证据：{eids}）")
    else:
        lines.append("- 当前没有完全通过证据校验的核心灾情结论。")
    lines.append("")

    lines.append("## 3. 分区评估结果")
    if qualified_findings:
        for item in qualified_findings:
            finding = item.get("finding") or "该结论仅能部分支持。"
            eids = ", ".join(item.get("evidence_ids", [])) or "未列出"
            reason = item.get("reason", "")
            lines.append(f"- {finding}（部分支持，证据：{eids}）。{reason}")
    else:
        lines.append("- 当前没有需要限定表述的分区结论。")
    lines.append("")

    lines.append("## 4. 证据支撑与一致性校验")
    lines.append(f"- 已引用证据编号：{', '.join(source_evidence_ids) or '无'}。")
    lines.append(f"- 被排除的 claim 数量：{len(excluded_claims)}。")
    lines.append("- 被排除的 claim 仅作为一致性校验记录，不作为正式灾情结论。")
    lines.append("")

    lines.append("## 5. 证据局限与不可下结论事项")
    if limitations:
        for lim in limitations:
            lines.append(f"- {lim}")
    else:
        lines.append("- 当前证据主要来自遥感影像、模型掩码和结构化证据，仍需结合现场核查。")
    lines.append("- 人员伤亡、经济损失、政府响应、现场救援状态等内容需要外部数据或人工核验。")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    raw = Path(args.input).read_text(encoding="utf-8")
    obj = parse_json_loose(raw)

    platform = obj.get("platform_report_json", {})
    if not isinstance(platform, dict):
        platform = {}

    task_id = obj.get("task_id") or platform.get("task_id", "")

    new_obj = {
        "task_id": task_id,
        "platform_report_json": platform,
        "markdown_report": rebuild_markdown_from_platform(platform, task_id)
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(new_obj, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("saved:", args.output)

if __name__ == "__main__":
    main()
