"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle, XCircle, ExternalLink } from "lucide-react";
import { getCases, overrideDecision } from "@/lib/api";
import type { CaseRecord } from "@/lib/types";
import AuditLog from "@/components/AuditLog";

interface OverrideModalProps {
  caseId: string;
  decision: "APPROVE" | "REJECT";
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}

function OverrideModal({ caseId, decision, onConfirm, onCancel }: OverrideModalProps) {
  const [reason, setReason] = useState("");
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-1">
          {decision === "APPROVE" ? "Approve" : "Reject"} case
        </h3>
        <p className="text-sm text-gray-500 mb-4 font-mono">{caseId.slice(0, 8)}…</p>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Reason for override (optional)"
          rows={3}
          className="w-full text-sm border border-gray-300 rounded-md p-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
        />
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(reason)}
            className={`px-4 py-2 text-sm text-white rounded-md font-medium ${
              decision === "APPROVE"
                ? "bg-green-600 hover:bg-green-700"
                : "bg-red-600 hover:bg-red-700"
            }`}
          >
            Confirm {decision === "APPROVE" ? "Approval" : "Rejection"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface CaseRowProps {
  record: CaseRecord;
  onOverride: (decision: "APPROVE" | "REJECT", reason: string) => Promise<void>;
  busy: boolean;
}

function EscalatedCaseRow({ record, onOverride, busy }: CaseRowProps) {
  const [modal, setModal] = useState<"APPROVE" | "REJECT" | null>(null);
  const [expanded, setExpanded] = useState(false);

  async function confirm(reason: string) {
    if (!modal) return;
    setModal(null);
    await onOverride(modal, reason);
  }

  return (
    <>
      {modal && (
        <OverrideModal
          caseId={record.case_id}
          decision={modal}
          onConfirm={confirm}
          onCancel={() => setModal(null)}
        />
      )}
      <div className="bg-white border border-yellow-200 rounded-lg overflow-hidden">
        <div className="px-4 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Link
                  href={`/cases/${record.case_id}`}
                  className="font-mono text-sm text-blue-600 hover:underline flex items-center gap-1"
                >
                  {record.case_id.slice(0, 8)}…
                  <ExternalLink className="w-3 h-3" />
                </Link>
                <span className="text-sm text-gray-500">{record.file_name}</span>
              </div>
              {record.orchestrator_output && (
                <div className="mt-2 space-y-0.5">
                  {record.orchestrator_output.reasons.map((r, i) => (
                    <p key={i} className="text-xs text-gray-600">
                      {r}
                    </p>
                  ))}
                </div>
              )}
              <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
                {record.orchestrator_output && (
                  <>
                    <span>
                      Fraud: <strong className="text-gray-600">{record.orchestrator_output.fraud_score.toFixed(2)}</strong>
                    </span>
                    <span>
                      Coverage: <strong className="text-gray-600">{(record.orchestrator_output.coverage_percentage * 100).toFixed(0)}%</strong>
                    </span>
                  </>
                )}
                <span>
                  Submitted {new Date(record.created_at).toLocaleString()}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                disabled={busy}
                onClick={() => setModal("APPROVE")}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-md disabled:opacity-50 transition-colors"
              >
                <CheckCircle className="w-4 h-4" />
                Approve
              </button>
              <button
                disabled={busy}
                onClick={() => setModal("REJECT")}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md disabled:opacity-50 transition-colors"
              >
                <XCircle className="w-4 h-4" />
                Reject
              </button>
            </div>
          </div>
        </div>

        {record.audit_log.length > 0 && (
          <div className="border-t border-gray-100">
            <button
              onClick={() => setExpanded((e) => !e)}
              className="w-full px-4 py-2 text-xs text-gray-500 hover:bg-gray-50 text-left transition-colors"
            >
              {expanded ? "Hide" : "Show"} audit log ({record.audit_log.length}{" "}
              {record.audit_log.length === 1 ? "entry" : "entries"})
            </button>
            {expanded && (
              <div className="px-4 pb-4">
                <AuditLog entries={record.audit_log} />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

export default function ReviewPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchEscalated = useCallback(async () => {
    try {
      const data = await getCases(1, "ESCALATED", 100);
      setCases(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load cases");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEscalated();
  }, [fetchEscalated]);

  async function handleOverride(
    caseId: string,
    decision: "APPROVE" | "REJECT",
    reason: string
  ) {
    setBusyId(caseId);
    try {
      await overrideDecision(caseId, decision, reason);
      await fetchEscalated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Override failed");
    } finally {
      setBusyId(null);
    }
  }

  if (loading)
    return (
      <div className="py-16 text-center text-gray-400">
        Loading review queue…
      </div>
    );

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Review Queue</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          {cases.length} escalated case{cases.length !== 1 ? "s" : ""} awaiting
          manual review
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          {error}
        </div>
      )}

      {cases.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-16 text-center">
          <p className="text-gray-500">No cases require review.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {cases.map((c) => (
            <EscalatedCaseRow
              key={c.case_id}
              record={c}
              busy={busyId === c.case_id}
              onOverride={(decision, reason) =>
                handleOverride(c.case_id, decision, reason)
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
