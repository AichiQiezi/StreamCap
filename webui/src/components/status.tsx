import { Loader2 } from "lucide-react";
import type { Rec, RecState } from "@/lib/types";
import { cx } from "./ui";

export const STATE_META: Record<RecState, { label: string; color: string; order: number }> = {
  recording: { label: "录制中", color: "var(--rec)", order: 0 },
  live: { label: "直播中", color: "var(--live)", order: 1 },
  error: { label: "异常", color: "var(--err)", order: 2 },
  checking: { label: "检测中", color: "var(--fg-3)", order: 3 },
  scheduled: { label: "等待时段", color: "var(--sched)", order: 4 },
  offline: { label: "未开播", color: "var(--fg-3)", order: 5 },
  paused: { label: "已暂停", color: "var(--fg-3)", order: 6 },
};

const ERROR_TEXT: Record<string, string> = {
  LIVE_STATUS_CHECK_ERROR: "检测失败",
  RECORDING_ERROR: "录制出错",
  NOT_RECORDING_SPACE: "磁盘空间不足",
};

export function stateLabel(r: Rec): string {
  if (r.state === "error") return ERROR_TEXT[r.status_info ?? ""] ?? "异常";
  if (r.state === "live" && r.only_notify_no_record) return "直播中 · 仅通知";
  return STATE_META[r.state].label;
}

export function StatusDot({ state, className }: { state: RecState; className?: string }) {
  if (state === "checking") return <Loader2 className={cx("size-3 animate-spin text-fg-3", className)} />;
  const color = STATE_META[state].color;
  return (
    <span
      className={cx(
        "inline-block size-2 shrink-0 rounded-full",
        state === "recording" && "animate-rec",
        state === "paused" && "border-[1.5px] border-current bg-transparent text-fg-3",
        className,
      )}
      style={state === "paused" ? undefined : { background: color, boxShadow: state === "recording" ? `0 0 0 3px color-mix(in srgb, ${color} 22%, transparent)` : undefined }}
    />
  );
}

export function StatusPill({ r }: { r: Rec }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[12px] font-medium" style={{ color: r.state === "offline" || r.state === "paused" || r.state === "checking" ? "var(--fg-2)" : STATE_META[r.state].color }}>
      <StatusDot state={r.state} />
      {stateLabel(r)}
    </span>
  );
}
