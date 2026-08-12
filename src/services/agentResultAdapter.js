const supportedStatuses = new Set([
  'supported',
  'partially_supported',
  'unsupported',
  'contradicted',
  'exaggerated',
])

const pendingStatuses = new Set([
  'human_review_required',
  'model_output_invalid',
])

export const reportMarkdownHeadings = {
  zh: ['报告摘要', '核心灾情指标', '分区评估结果', '证据支撑与一致性校验', '证据局限与不可下结论事项'],
  en: ['Executive Summary', 'Key Disaster Indicators', 'Regional Assessment', 'Evidence Support and Consistency Check', 'Limitations and Non-conclusive Items'],
}

function array(value) {
  return Array.isArray(value) ? value : []
}

function localizedText(value, language = 'zh-CN') {
  if (typeof value === 'string') return value
  if (!value || typeof value !== 'object') return ''
  return value[language]
    ?? value[language === 'zh-CN' ? 'zh' : 'en']
    ?? value['en-US']
    ?? value['zh-CN']
    ?? ''
}

function normalizeClaimCheck(check, fallbackStatus = '') {
  const resolutionState = check.resolution_state ?? ''
  const rawStatus = check.support_status ?? check.status ?? resolutionState ?? fallbackStatus
  const status = supportedStatuses.has(rawStatus) || pendingStatuses.has(rawStatus)
    ? rawStatus
    : fallbackStatus || 'unsupported'

  return {
    id: check.claim_id,
    text: check.atomic_claim ?? check.claim ?? check.claim_text ?? check.text ?? '',
    claimType: check.claim_type ?? null,
    status,
    resolutionState,
    failureCategory: check.failure_category ?? null,
    humanReviewRequired: check.human_review_required === true || status === 'human_review_required',
    evidenceRefs: array(check.evidence_ids ?? check.evidence_refs),
    reason: check.reason ?? '',
    suggestedRevision: check.suggested_revision ?? null,
  }
}

function packageClaims(verifiedPackage) {
  if (!verifiedPackage) return []
  return [
    ...array(verifiedPackage.accepted_claims).map((item) => normalizeClaimCheck(item, 'supported')),
    ...array(verifiedPackage.revised_claims).map((item) => normalizeClaimCheck(item, 'partially_supported')),
    ...array(verifiedPackage.rejected_claims).map((item) => normalizeClaimCheck(item, 'unsupported')),
    ...array(verifiedPackage.pending_claims).map((item) => normalizeClaimCheck(item, item.resolution_state || 'human_review_required')),
  ]
}

function verificationOverallStatus(claimChecks, checkResult, verifiedPackage) {
  if (checkResult?.overall_status) return checkResult.overall_status
  const hasAttention = claimChecks.some((claim) =>
    ['unsupported', 'contradicted', 'exaggerated', 'human_review_required', 'model_output_invalid'].includes(claim.status),
  )
  return hasAttention || array(verifiedPackage?.pending_claims).length ? 'warning' : 'pass'
}

export function normalizeEvidenceVerification(payload) {
  if (!payload) return null

  const checkResult = payload.check_result ?? payload.verification ?? payload
  const verifiedPackage = payload.verified_evidence_package
    ?? checkResult.verified_evidence_package
    ?? null
  const legacyChecks = array(checkResult.claim_checks ?? checkResult.atomic_claims)
  const claimChecks = legacyChecks.length
    ? legacyChecks.map((item) => normalizeClaimCheck(item))
    : packageClaims(verifiedPackage)
  const packageSummary = verifiedPackage?.summary ?? {}
  const pendingClaims = array(verifiedPackage?.pending_claims)
  const humanReviewClaimCount = pendingClaims.filter((item) =>
    item.resolution_state === 'human_review_required' || item.human_review_required === true,
  ).length
  const modelOutputInvalidCount = pendingClaims.filter((item) =>
    item.resolution_state === 'model_output_invalid' || item.failure_category === 'format_contract',
  ).length

  return {
    taskId: payload.task_id
      ?? payload.job_id
      ?? checkResult.task_id
      ?? verifiedPackage?.task_info?.scene_uid
      ?? null,
    capability: 'evidence_verification',
    sourceAgentId: payload.source_agent_id ?? payload.agent_code ?? 'agent3',
    sourceVersion: payload.source_version ?? payload.agent3_version ?? 'Agent3-V5.2.1',
    overallStatus: verificationOverallStatus(claimChecks, checkResult, verifiedPackage),
    attentionSummary: {
      humanReviewClaimCount,
      modelOutputInvalidCount,
      otherPendingClaimCount: Math.max(0, pendingClaims.length - humanReviewClaimCount - modelOutputInvalidCount),
    },
    claimChecks,
    groups: {
      supported: checkResult.supported_claims ?? claimChecks.filter((item) => item.status === 'supported'),
      partiallySupported: checkResult.partially_supported_claims ?? claimChecks.filter((item) => item.status === 'partially_supported'),
      unsupported: checkResult.unsupported_claims ?? claimChecks.filter((item) => item.status === 'unsupported'),
      contradicted: checkResult.contradicted_claims ?? claimChecks.filter((item) => item.status === 'contradicted'),
      exaggerated: checkResult.exaggerated_claims ?? claimChecks.filter((item) => item.status === 'exaggerated'),
    },
    revisionSuggestions: array(checkResult.revision_suggestions),
    verifiedEvidencePackage: verifiedPackage
      ? {
          schemaVersion: verifiedPackage.schema_version ?? null,
          summary: packageSummary,
          acceptedClaims: array(verifiedPackage.accepted_claims),
          revisedClaims: array(verifiedPackage.revised_claims ?? verifiedPackage.qualified_claims),
          rejectedClaims: array(verifiedPackage.rejected_claims),
          pendingClaims,
          sourceEvidenceIds: array(verifiedPackage.source_evidence_ids),
          limitations: array(verifiedPackage.limitations),
        }
      : null,
  }
}

function reportFindingText(item, language) {
  return localizedText(item?.text ?? item, language)
}

function normalizeReportFindings(platformReport) {
  const sections = platformReport.sections ?? {}
  const currentFindings = [
    ...array(sections.key_disaster_indicators),
    ...array(sections.regional_assessment),
  ]
  if (currentFindings.length) {
    return {
      keyFindings: currentFindings.filter((item) => item.support_status === 'supported'),
      revisedFindings: currentFindings.filter((item) => item.support_status !== 'supported'),
      excludedClaims: array(sections.limitations_and_nonconclusive_items).filter((item) => item.type === 'rejected_claim'),
      limitations: array(sections.limitations_and_nonconclusive_items).filter((item) => item.type !== 'rejected_claim'),
    }
  }
  return {
    keyFindings: array(platformReport.key_findings),
    revisedFindings: array(platformReport.revised_findings ?? platformReport.qualified_findings),
    excludedClaims: array(platformReport.excluded_claims),
    limitations: array(platformReport.limitations),
  }
}

function hasHeadings(markdown, language) {
  if (!markdown) return false
  return reportMarkdownHeadings[language].every((heading) => markdown.includes(heading))
}

export function normalizeGeneratedReport(payload) {
  if (!payload) return null

  const platformReport = payload.platform_report_json ?? payload.report ?? {}
  const markdownZh = payload.markdown_report_zh ?? payload.markdown_report ?? payload.markdown ?? ''
  const markdownEn = payload.markdown_report_en ?? ''
  const headingsZh = markdownZh ? hasHeadings(markdownZh, 'zh') : null
  const headingsEn = markdownEn ? hasHeadings(markdownEn, 'en') : null
  const suppliedHeadingChecks = [headingsZh, headingsEn].filter((value) => value !== null)
  const findings = normalizeReportFindings(platformReport)
  const reportSummary = platformReport.report_summary ?? platformReport.data_basis ?? {}
  const reviewInfo = platformReport.review_info ?? {}
  const executiveSummary = platformReport.sections?.executive_summary
    ?? platformReport.final_conclusion
    ?? ''
  const hasAttention = Boolean(
    reviewInfo.attention_required
    || reviewInfo.human_review_required
    || Number(reportSummary.pending_count ?? reportSummary.pending ?? 0) > 0,
  )

  return {
    taskId: payload.task_id
      ?? payload.job_id
      ?? platformReport.task_info?.scene_uid
      ?? platformReport.task_id
      ?? null,
    capability: 'report_generation',
    sourceAgentId: payload.source_agent_id ?? payload.agent_code ?? 'agent4',
    sourceVersion: payload.source_version ?? payload.agent4_version ?? 'Agent4-V3',
    overallStatus: platformReport.overall_status ?? (hasAttention ? 'warning' : 'pass'),
    reportType: platformReport.report_type ?? 'preliminary_remote_sensing_assessment',
    reportVersion: platformReport.report_version ?? platformReport.schema_version ?? null,
    reportSummary,
    reviewInfo,
    dataBasis: platformReport.data_basis ?? reportSummary,
    keyFindings: findings.keyFindings,
    revisedFindings: findings.revisedFindings,
    excludedClaims: findings.excludedClaims,
    limitations: findings.limitations,
    finalConclusion: localizedText(executiveSummary, 'zh-CN'),
    finalConclusionEn: localizedText(executiveSummary, 'en-US'),
    markdownZh,
    markdownEn,
    // Compatibility for existing callers: Chinese is the default download.
    markdownReport: markdownZh || markdownEn,
    hasFixedMarkdownSections: suppliedHeadingChecks.length > 0 && suppliedHeadingChecks.every(Boolean),
    hasFixedMarkdownSectionsZh: headingsZh,
    hasFixedMarkdownSectionsEn: headingsEn,
    findingText: reportFindingText,
  }
}
