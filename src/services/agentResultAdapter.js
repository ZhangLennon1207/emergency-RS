const supportedStatuses = new Set([
  'supported',
  'partially_supported',
  'unsupported',
  'contradicted',
  'exaggerated',
])

export const reportMarkdownHeadings = [
  '## 1. 报告摘要',
  '## 2. 核心灾情指标',
  '## 3. 分区评估结果',
  '## 4. 证据支撑与一致性校验',
  '## 5. 证据局限与不可下结论事项',
]

function normalizeClaimCheck(check) {
  const status = check.support_status ?? check.status ?? 'unsupported'

  return {
    id: check.claim_id,
    text: check.claim ?? check.claim_text ?? check.text ?? '',
    status: supportedStatuses.has(status) ? status : 'unsupported',
    evidenceRefs: check.evidence_ids ?? check.evidence_refs ?? [],
    reason: check.reason ?? '',
    suggestedRevision: check.suggested_revision ?? null,
  }
}

export function normalizeEvidenceVerification(payload) {
  if (!payload) return null

  const checkResult = payload.check_result ?? payload.verification ?? payload
  const verifiedPackage = payload.verified_evidence_package ?? null

  return {
    taskId: payload.task_id ?? checkResult.task_id ?? null,
    capability: 'evidence_verification',
    sourceAgentId: payload.source_agent_id ?? 'agent4',
    sourceVersion: payload.source_version ?? 'Agent4-V4',
    overallStatus: checkResult.overall_status ?? 'warning',
    claimChecks: (checkResult.claim_checks ?? checkResult.atomic_claims ?? []).map(normalizeClaimCheck),
    groups: {
      supported: checkResult.supported_claims ?? [],
      partiallySupported: checkResult.partially_supported_claims ?? [],
      unsupported: checkResult.unsupported_claims ?? [],
      contradicted: checkResult.contradicted_claims ?? [],
      exaggerated: checkResult.exaggerated_claims ?? [],
    },
    revisionSuggestions: checkResult.revision_suggestions ?? [],
    verifiedEvidencePackage: verifiedPackage
      ? {
          overallStatus: verifiedPackage.overall_status ?? 'warning',
          acceptedClaims: verifiedPackage.accepted_claims ?? [],
          qualifiedClaims: verifiedPackage.qualified_claims ?? [],
          rejectedClaims: verifiedPackage.rejected_claims ?? [],
          sourceEvidenceIds: verifiedPackage.source_evidence_ids ?? [],
          limitations: verifiedPackage.limitations ?? [],
        }
      : null,
  }
}

export function normalizeGeneratedReport(payload) {
  if (!payload) return null

  const platformReport = payload.platform_report_json ?? payload.report ?? {}
  const markdownReport = payload.markdown_report ?? payload.markdown ?? ''

  return {
    taskId: payload.task_id ?? platformReport.task_id ?? null,
    capability: 'report_generation',
    sourceAgentId: payload.source_agent_id ?? 'agent5',
    sourceVersion: payload.source_version ?? 'Agent5-V2',
    overallStatus: platformReport.overall_status ?? 'warning',
    reportType: platformReport.report_type ?? 'remote_sensing_disaster_assessment',
    reportVersion: platformReport.report_version ?? null,
    dataBasis: platformReport.data_basis ?? {},
    keyFindings: platformReport.key_findings ?? [],
    qualifiedFindings: platformReport.qualified_findings ?? [],
    excludedClaims: platformReport.excluded_claims ?? [],
    limitations: platformReport.limitations ?? [],
    finalConclusion: platformReport.final_conclusion ?? '',
    markdownReport,
    hasFixedMarkdownSections: reportMarkdownHeadings.every((heading) => markdownReport.includes(heading)),
  }
}
