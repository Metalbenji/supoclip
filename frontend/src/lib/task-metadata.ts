const ACTIVE_TASK_STATUSES = new Set(["processing", "queued"]);
const REVIEW_PENDING_STATUSES = new Set(["awaiting_review"]);

type TaskRuntimeInfo = Record<string, unknown> | null | undefined;

function coerceFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function formatElapsedDuration(totalSeconds: number): string {
  let remainingSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(remainingSeconds / 3600);
  remainingSeconds %= 3600;
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;

  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function isHttpUrl(value: string | null | undefined): boolean {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

export function formatSourceTypeLabel(sourceType?: string | null): string {
  if (!sourceType) return "Source";
  if (sourceType === "video_url") return "Video URL";
  return sourceType.charAt(0).toUpperCase() + sourceType.slice(1);
}

function getActiveProcessingSeconds(
  runtimeInfo: TaskRuntimeInfo,
  status: string | null | undefined,
  nowMs: number,
): number | null {
  if (!runtimeInfo || typeof runtimeInfo !== "object") {
    return null;
  }
  const storedSeconds = coerceFiniteNumber(runtimeInfo.active_processing_seconds) ?? 0;
  const startedAtMs = coerceFiniteNumber(runtimeInfo.processing_window_started_at_ms);
  if (startedAtMs === null) {
    return storedSeconds;
  }
  if (!ACTIVE_TASK_STATUSES.has(status || "")) {
    return storedSeconds;
  }
  return storedSeconds + Math.max(0, (nowMs - startedAtMs) / 1000);
}

function getReviewWaitSeconds(
  runtimeInfo: TaskRuntimeInfo,
  status: string | null | undefined,
  nowMs: number,
): number | null {
  if (!runtimeInfo || typeof runtimeInfo !== "object") {
    return null;
  }
  const startedAtMs = coerceFiniteNumber(runtimeInfo.review_started_at_ms);
  if (startedAtMs === null) {
    return null;
  }
  const completedAtMs = coerceFiniteNumber(runtimeInfo.review_completed_at_ms);
  const endedAtMs = completedAtMs ?? (REVIEW_PENDING_STATUSES.has(status || "") ? nowMs : null);
  if (endedAtMs === null) {
    return null;
  }
  return Math.max(0, (endedAtMs - startedAtMs) / 1000);
}

export function getTaskRuntimeSummary(
  createdAt: string | null | undefined,
  updatedAt: string | null | undefined,
  status: string | null | undefined,
  runtimeInfo: TaskRuntimeInfo,
  nowMs: number = Date.now(),
): { processing: string; reviewWait: string | null } {
  const activeProcessingSeconds = getActiveProcessingSeconds(runtimeInfo, status, nowMs);
  const reviewWaitSeconds = getReviewWaitSeconds(runtimeInfo, status, nowMs);

  if (activeProcessingSeconds !== null) {
    return {
      processing: formatElapsedDuration(activeProcessingSeconds),
      reviewWait: reviewWaitSeconds !== null ? formatElapsedDuration(reviewWaitSeconds) : null,
    };
  }

  return {
    processing: formatTaskRuntime(createdAt, updatedAt, status, nowMs),
    reviewWait: null,
  };
}

export function formatTaskRuntime(
  createdAt: string | null | undefined,
  updatedAt: string | null | undefined,
  status: string | null | undefined,
  nowMs: number = Date.now(),
): string {
  if (!createdAt) return "n/a";
  const started = new Date(createdAt);
  if (Number.isNaN(started.getTime())) return "n/a";

  const shouldUseNow = ACTIVE_TASK_STATUSES.has(status || "") || !updatedAt;
  const ended = shouldUseNow ? new Date(nowMs) : new Date(updatedAt);
  if (Number.isNaN(ended.getTime())) return "n/a";

  return formatElapsedDuration((ended.getTime() - started.getTime()) / 1000);
}
