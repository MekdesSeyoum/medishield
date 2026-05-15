"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

type PanelStatus = "pass" | "fail" | "warn" | "na";

interface Props {
  title: string;
  status?: PanelStatus;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const DOT: Record<PanelStatus, string> = {
  pass: "bg-green-500",
  fail: "bg-red-500",
  warn: "bg-yellow-500",
  na: "bg-gray-300",
};

export default function AgentPanel({
  title,
  status = "na",
  defaultOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-white">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 text-left transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${DOT[status]}`} />
          <span className="font-medium text-sm text-gray-900">{title}</span>
        </div>
        {open ? (
          <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-gray-400 shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-sm text-gray-700">
          {children}
        </div>
      )}
    </div>
  );
}
