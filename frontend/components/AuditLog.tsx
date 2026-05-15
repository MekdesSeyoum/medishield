import type { AuditEntry } from "@/lib/types";

interface Props {
  entries: AuditEntry[];
}

export default function AuditLog({ entries }: Props) {
  if (entries.length === 0) return null;
  return (
    <div className="relative pl-6">
      <div className="absolute left-2 top-2 bottom-2 w-px bg-gray-200" />
      <div className="space-y-3">
        {entries.map((entry, i) => (
          <div key={i} className="relative">
            <div
              className={`absolute -left-4 top-2 w-3 h-3 rounded-full border-2 border-gray-50 ${
                entry.action === "MANUAL_OVERRIDE" ? "bg-blue-500" : "bg-gray-400"
              }`}
            />
            <div className="bg-white border border-gray-200 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span
                  className={`text-xs font-medium ${
                    entry.action === "MANUAL_OVERRIDE"
                      ? "text-blue-600"
                      : "text-gray-500"
                  }`}
                >
                  {entry.action === "MANUAL_OVERRIDE"
                    ? `Manual override by ${entry.actor}`
                    : `Pipeline decision (${entry.actor})`}
                </span>
                <span className="text-xs text-gray-400">
                  {new Date(entry.timestamp).toLocaleString()}
                </span>
              </div>
              <p className="text-sm font-semibold text-gray-900">{entry.decision}</p>
              {entry.reason && (
                <p className="text-xs text-gray-500 mt-0.5">{entry.reason}</p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
