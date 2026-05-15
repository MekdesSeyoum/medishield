"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { getCase, getDocumentUrl } from "@/lib/api";
import type { CaseRecord } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import AgentPanel from "@/components/AgentPanel";
import DecisionBanner from "@/components/DecisionBanner";
import AuditLog from "@/components/AuditLog";

function KV({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex gap-2 py-0.5">
      <dt className="text-xs font-medium text-gray-500 w-28 shrink-0">{label}</dt>
      <dd className="text-xs text-gray-900 break-words">{value}</dd>
    </div>
  );
}

function Empty() {
  return <p className="text-xs text-gray-400 italic">Not yet processed</p>;
}

export default function CaseDetailPage() {
  const { case_id } = useParams<{ case_id: string }>();
  const [caseData, setCaseData] = useState<CaseRecord | null>(null);
  const [docUrl, setDocUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [c, doc] = await Promise.all([
          getCase(case_id),
          getDocumentUrl(case_id).catch(() => null),
        ]);
        setCaseData(c);
        if (doc) setDocUrl(doc.url);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load case");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [case_id]);

  if (loading)
    return (
      <div className="py-16 text-center text-gray-400">Loading case…</div>
    );
  if (error || !caseData)
    return (
      <div className="py-16 text-center text-red-500">
        {error ?? "Case not found."}
      </div>
    );

  const { classifier_output, kyc_output, claims_output, policy_output, fraud_output, orchestrator_output } =
    caseData;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <Link
          href="/dashboard"
          className="text-gray-400 hover:text-gray-600 transition-colors"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-xl font-bold text-gray-900">Case</h1>
        <span className="font-mono text-gray-400 text-sm">{caseData.case_id}</span>
        <StatusBadge status={caseData.status} />
      </div>

      {orchestrator_output && (
        <DecisionBanner output={orchestrator_output} className="mb-5" />
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {/* Left — Document viewer */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
            <p className="text-sm font-medium text-gray-800 truncate">
              {caseData.file_name}
            </p>
            <p className="text-xs text-gray-500">{caseData.mime_type}</p>
          </div>
          <div className="p-4 flex items-center justify-center bg-gray-50 min-h-[300px]">
            {docUrl ? (
              caseData.mime_type.startsWith("image/") ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={docUrl}
                  alt={caseData.file_name}
                  className="max-w-full max-h-[600px] object-contain rounded shadow"
                />
              ) : (
                <iframe
                  src={docUrl}
                  title={caseData.file_name}
                  className="w-full h-[600px] rounded"
                />
              )
            ) : (
              <p className="text-sm text-gray-400 italic">
                Document preview unavailable
              </p>
            )}
          </div>
        </div>

        {/* Right — Agent output panels */}
        <div className="space-y-2">
          <AgentPanel
            title="Classifier"
            status={classifier_output ? "pass" : "na"}
            defaultOpen={!!classifier_output}
          >
            {classifier_output ? (
              <dl>
                <KV label="Doc type" value={classifier_output.document_type} />
                <KV
                  label="Confidence"
                  value={`${(classifier_output.confidence * 100).toFixed(0)}%`}
                />
                <KV label="Pages" value={String(classifier_output.page_count)} />
                <KV
                  label="Handwritten"
                  value={classifier_output.is_handwritten ? "Yes" : "No"}
                />
                {classifier_output.routing_hints.length > 0 && (
                  <KV
                    label="Hints"
                    value={classifier_output.routing_hints.join(", ")}
                  />
                )}
              </dl>
            ) : (
              <Empty />
            )}
          </AgentPanel>

          <AgentPanel
            title="KYC"
            status={
              kyc_output ? (kyc_output.kyc_passed ? "pass" : "fail") : "na"
            }
          >
            {kyc_output ? (
              <dl>
                <KV
                  label="Passed"
                  value={
                    <span
                      className={
                        kyc_output.kyc_passed
                          ? "text-green-700 font-medium"
                          : "text-red-700 font-medium"
                      }
                    >
                      {kyc_output.kyc_passed ? "Yes" : "No"}
                    </span>
                  }
                />
                <KV
                  label="Confidence"
                  value={`${(kyc_output.confidence * 100).toFixed(0)}%`}
                />
                {kyc_output.flags.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Flags
                    </p>
                    <div className="flex flex-wrap gap-1">
                      {kyc_output.flags.map((f, i) => (
                        <span
                          key={i}
                          className="inline-block bg-red-100 text-red-700 text-xs px-2 py-0.5 rounded"
                        >
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </dl>
            ) : (
              <Empty />
            )}
          </AgentPanel>

          <AgentPanel
            title="Claims Extraction"
            status={
              claims_output
                ? claims_output.schema_valid
                  ? "pass"
                  : "warn"
                : "na"
            }
          >
            {claims_output ? (
              <div>
                <KV
                  label="Schema valid"
                  value={claims_output.schema_valid ? "Yes" : "No"}
                />
                {claims_output.validation_errors.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Errors
                    </p>
                    {claims_output.validation_errors.map((e, i) => (
                      <p key={i} className="text-xs text-red-600">
                        {e}
                      </p>
                    ))}
                  </div>
                )}
                <div className="mt-2">
                  <p className="text-xs font-medium text-gray-500 mb-1">
                    Extracted fields
                  </p>
                  <pre className="text-xs bg-gray-100 p-2 rounded overflow-x-auto whitespace-pre-wrap break-words">
                    {JSON.stringify(claims_output.extracted_fields, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <Empty />
            )}
          </AgentPanel>

          <AgentPanel
            title="Policy"
            status={
              policy_output
                ? policy_output.covered
                  ? "pass"
                  : "fail"
                : "na"
            }
          >
            {policy_output ? (
              <dl>
                <KV
                  label="Covered"
                  value={
                    <span
                      className={
                        policy_output.covered
                          ? "text-green-700 font-medium"
                          : "text-red-700 font-medium"
                      }
                    >
                      {policy_output.covered ? "Yes" : "No"}
                    </span>
                  }
                />
                <KV
                  label="Coverage"
                  value={`${(policy_output.coverage_percentage * 100).toFixed(0)}%`}
                />
                <KV label="Clause" value={policy_output.policy_clause} />
                {policy_output.exclusions.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Exclusions
                    </p>
                    {policy_output.exclusions.map((e, i) => (
                      <p key={i} className="text-xs text-orange-700">
                        {e}
                      </p>
                    ))}
                  </div>
                )}
              </dl>
            ) : (
              <Empty />
            )}
          </AgentPanel>

          <AgentPanel
            title="Fraud Detection"
            status={
              fraud_output
                ? fraud_output.risk_level === "LOW"
                  ? "pass"
                  : fraud_output.risk_level === "HIGH"
                  ? "fail"
                  : "warn"
                : "na"
            }
          >
            {fraud_output ? (
              <dl>
                <KV label="Score" value={fraud_output.fraud_score.toFixed(2)} />
                <KV label="Risk level" value={fraud_output.risk_level} />
                {fraud_output.anomalies.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Anomalies
                    </p>
                    {fraud_output.anomalies.map((a, i) => (
                      <p key={i} className="text-xs text-orange-700 mt-0.5">
                        {a}
                      </p>
                    ))}
                  </div>
                )}
              </dl>
            ) : (
              <Empty />
            )}
          </AgentPanel>

          <AgentPanel
            title="Orchestrator Decision"
            status={
              orchestrator_output
                ? orchestrator_output.decision === "APPROVE"
                  ? "pass"
                  : orchestrator_output.decision === "REJECT"
                  ? "fail"
                  : "warn"
                : "na"
            }
            defaultOpen={!!orchestrator_output}
          >
            {orchestrator_output ? (
              <dl>
                <KV
                  label="Decision"
                  value={
                    <span className="font-semibold">
                      {orchestrator_output.decision}
                    </span>
                  }
                />
                <KV
                  label="Fraud score"
                  value={orchestrator_output.fraud_score.toFixed(2)}
                />
                <KV
                  label="Coverage"
                  value={`${(orchestrator_output.coverage_percentage * 100).toFixed(0)}%`}
                />
                {orchestrator_output.reasons.length > 0 && (
                  <div className="mt-2">
                    <p className="text-xs font-medium text-gray-500 mb-1">
                      Reasons
                    </p>
                    {orchestrator_output.reasons.map((r, i) => (
                      <p key={i} className="text-xs text-gray-700 mt-0.5">
                        {r}
                      </p>
                    ))}
                  </div>
                )}
              </dl>
            ) : (
              <Empty />
            )}
          </AgentPanel>
        </div>
      </div>

      {/* Audit log */}
      {caseData.audit_log.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Audit Log
          </h2>
          <AuditLog entries={caseData.audit_log} />
        </div>
      )}

      <div className="mt-6 text-xs text-gray-400">
        Created {new Date(caseData.created_at).toLocaleString()} · Last updated{" "}
        {new Date(caseData.updated_at).toLocaleString()}
      </div>
    </div>
  );
}
