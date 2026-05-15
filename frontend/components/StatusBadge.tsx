import type { CaseStatus } from "@/lib/types";

const CONFIG: Record<CaseStatus, { label: string; classes: string }> = {
  PENDING: { label: "Pending", classes: "bg-gray-100 text-gray-700" },
  PROCESSING: {
    label: "Processing",
    classes: "bg-blue-100 text-blue-700 animate-pulse",
  },
  APPROVED: { label: "Approved", classes: "bg-green-100 text-green-700" },
  DENIED: { label: "Denied", classes: "bg-red-100 text-red-700" },
  ESCALATED: { label: "Escalated", classes: "bg-yellow-100 text-yellow-800" },
  PENDING_INFO: {
    label: "Pending Info",
    classes: "bg-orange-100 text-orange-700",
  },
};

export default function StatusBadge({ status }: { status: CaseStatus }) {
  const { label, classes } = CONFIG[status] ?? {
    label: status,
    classes: "bg-gray-100 text-gray-700",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${classes}`}
    >
      {label}
    </span>
  );
}
