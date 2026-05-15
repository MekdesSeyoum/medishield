import type { OrchestratorOutput } from "@/lib/types";

const STYLE = {
  APPROVE: {
    label: "Approved",
    wrap: "bg-green-50 border-green-200",
    heading: "text-green-800",
    dot: "bg-green-500",
  },
  REJECT: {
    label: "Rejected",
    wrap: "bg-red-50 border-red-200",
    heading: "text-red-800",
    dot: "bg-red-500",
  },
  ESCALATE: {
    label: "Escalated for Review",
    wrap: "bg-yellow-50 border-yellow-200",
    heading: "text-yellow-800",
    dot: "bg-yellow-500",
  },
} as const;

interface Props {
  output: OrchestratorOutput;
  className?: string;
}

export default function DecisionBanner({ output, className = "" }: Props) {
  const s = STYLE[output.decision];
  return (
    <div className={`border rounded-lg p-4 ${s.wrap} ${className}`}>
      <div className="flex items-center gap-3 mb-2">
        <span className={`w-3 h-3 rounded-full shrink-0 ${s.dot}`} />
        <span className={`font-semibold ${s.heading}`}>{s.label}</span>
        <span className="text-sm text-gray-500 ml-1">
          Fraud score: <strong>{output.fraud_score.toFixed(2)}</strong> ·
          Coverage: <strong>{(output.coverage_percentage * 100).toFixed(0)}%</strong>
        </span>
      </div>
      <ul className="space-y-0.5 ml-6">
        {output.reasons.map((r, i) => (
          <li key={i} className="text-xs text-gray-700">
            {r}
          </li>
        ))}
      </ul>
    </div>
  );
}
