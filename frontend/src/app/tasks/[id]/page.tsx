"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useSession } from "@/lib/auth-client";
import { ArrowLeft, Download, Clock, Timer, Star, AlertCircle, Trash2, Edit2, X, Check } from "lucide-react";
import Link from "next/link";
import DynamicVideoPlayer from "@/components/dynamic-video-player";
import DraftTimelineEditor, { type TimelineZoomLevel } from "@/components/draft-timeline-editor";
import { formatAiFocusTag } from "@/lib/ai-focus-tags";
import { formatSourceTypeLabel, getTaskRuntimeSummary, isHttpUrl } from "@/lib/task-metadata";

interface Clip {
  id: string;
  filename: string;
  file_path: string;
  start_time: string;
  end_time: string;
  duration: number;
  text: string;
  relevance_score: number;
  reasoning: string;
  clip_order: number;
  created_at: string;
  video_url: string;
}

interface DraftClip {
  id: string;
  clip_order: number;
  start_time: string;
  end_time: string;
  duration: number;
  original_text: string;
  edited_text: string;
  relevance_score: number;
  review_score?: number;
  feedback_score_adjustment?: number;
  feedback_signals_json?: {
    version?: number;
    selected?: boolean;
    deselected?: boolean;
    deleted?: boolean;
    created_by_user?: boolean;
    timing_changed?: boolean;
    timing_shift_seconds?: number;
    text_edited?: boolean;
  } | null;
  reasoning: string;
  is_selected: boolean;
  created_by_user?: boolean;
  edited_word_timings_json?: Array<{ text: string; start: number; end: number }> | null;
  framing_metadata_json?: {
    face_detected?: boolean;
    face_detection_rate?: number;
    primary_face_area_ratio?: number | null;
    dominant_face_count?: number;
    multi_face_frames_rate?: number;
    crop_confidence?: "high" | "medium" | "low" | "none" | string;
    suggested_crop_mode?: "face" | "center" | string;
    score_adjustment?: number;
    sampled_frames?: number;
    raw_face_frames?: number;
    reliable_face_frames?: number;
    detector_backend?: string;
    detection_state?: "strong" | "weak" | "none" | string;
    filter_reason_counts?: {
      too_small?: number;
      too_large?: number;
      low_confidence?: number;
      off_frame?: number;
    } | null;
    face_detection_mode?: "balanced" | "more_faces" | string;
    fallback_crop_position?: "center" | "left_center" | "right_center" | string;
  } | null;
  framing_mode_override?: "auto" | "prefer_face" | "fixed_position" | string;
  preview_url?: string;
  selection_rationale?: {
    transcript_relevance?: number;
    framing_quality?: "strong" | "weak" | "none" | string;
    hook_score?: number;
    review_adjustments?: string[];
  } | null;
  created_at?: string;
  updated_at?: string;
}

interface DraftOverlapConflict {
  left_id: string;
  right_id: string;
  left_label: string;
  right_label: string;
  left_start_time: string;
  left_end_time: string;
  right_start_time: string;
  right_end_time: string;
}

interface TaskDetails {
  id: string;
  user_id: string;
  source_id: string;
  source_title: string;
  source_type: string;
  source_url?: string | null;
  status: string;
  progress?: number;
  progress_message?: string;
  clips_count: number;
  created_at: string;
  updated_at: string;
  font_family?: string;
  font_size?: number;
  font_color?: string;
  transitions_enabled?: boolean;
  transcription_provider?: string;
  ai_provider?: string;
  ai_focus_tags?: string[];
  review_before_render_enabled?: boolean;
  timeline_editor_enabled?: boolean;
  processing_profile?: string;
  workflow_source?: string;
  saved_workflow_id?: string | null;
  workflow_name_snapshot?: string | null;
  runtime_info?: Record<string, unknown>;
  failure_code?: string | null;
  failure_hint?: string | null;
  stage_checkpoint?: string;
  retryable_from_stages?: string[];
  diagnostics?: {
    queue_target?: string;
    worker_type?: string;
    transcription?: {
      provider?: string;
      model?: string | null;
      device_preference?: string | null;
    };
    ai?: {
      provider?: string;
      model?: string | null;
    };
    runtime_target?: string | null;
    fallback_reason?: string | null;
    current_stage?: string | null;
    latest_stage_metadata?: Record<string, unknown> | null;
  };
}

interface TranscriptProgressMetadata {
  mode?: "chunked" | "single";
  chunk_index?: number;
  chunk_total?: number;
  chunks_completed?: number;
  chunk_start_seconds?: number;
  chunk_end_seconds?: number;
  chunk_elapsed_seconds?: number;
  total_elapsed_seconds?: number;
  average_chunk_seconds?: number;
}

interface TaskProgressMetadata extends TranscriptProgressMetadata {
  stage?: StageKey;
  stage_progress?: number;
  cached?: boolean;
  stage_label?: string;
  clip_index?: number;
  clip_total?: number;
  clip_started?: boolean;
  clip_completed?: boolean;
  start_time?: string;
  end_time?: string;
  filename?: string;
  success?: boolean;
}

type FramingModeOverride = "auto" | "prefer_face" | "fixed_position";
type FramingFilter = "all" | "best" | "weak" | "none";

function normalizeFramingModeOverride(value: unknown): FramingModeOverride {
  if (value === "disable_face_crop") {
    return "fixed_position";
  }
  if (value === "prefer_face" || value === "fixed_position") {
    return value;
  }
  return "auto";
}

function normalizeFallbackCropPosition(value: unknown): "center" | "left_center" | "right_center" {
  if (value === "left_center" || value === "right_center") {
    return value;
  }
  return "center";
}

function formatFallbackCropPosition(value: unknown): string {
  const normalized = normalizeFallbackCropPosition(value);
  if (normalized === "left_center") {
    return "left-center";
  }
  if (normalized === "right_center") {
    return "right-center";
  }
  return "center";
}

function getTaskWorkflowLabel(task: TaskDetails): string | null {
  if (typeof task.workflow_name_snapshot === "string" && task.workflow_name_snapshot.trim().length > 0) {
    return task.workflow_name_snapshot.trim();
  }
  if (typeof task.processing_profile === "string" && task.processing_profile.trim().length > 0) {
    return task.processing_profile.replace(/_/g, " ");
  }
  if (task.workflow_source === "custom") {
    return "Custom";
  }
  return null;
}

function getFramingStrength(metadata?: DraftClip["framing_metadata_json"]): "strong" | "weak" | "none" {
  const detectionState = String(metadata?.detection_state || "");
  if (detectionState === "strong") {
    return "strong";
  }
  if (detectionState === "weak") {
    return "weak";
  }
  const confidence = String(metadata?.crop_confidence || "none");
  if (confidence === "high" || confidence === "medium") {
    return "strong";
  }
  if (Boolean(metadata?.face_detected)) {
    return "weak";
  }
  return "none";
}

function getFramingBadgeLabel(metadata?: DraftClip["framing_metadata_json"]): string {
  const strength = getFramingStrength(metadata);
  if (strength === "strong") return "Face: strong";
  if (strength === "weak") return "Face: weak";
  return "Face: none";
}

function getFramingBadgeClass(metadata?: DraftClip["framing_metadata_json"]): string {
  const strength = getFramingStrength(metadata);
  if (strength === "strong") return "bg-green-100 text-green-800";
  if (strength === "weak") return "bg-amber-100 text-amber-800";
  return "bg-slate-100 text-slate-700";
}

function getFramingExplanation(metadata?: DraftClip["framing_metadata_json"]): string {
  const strength = getFramingStrength(metadata);
  if (strength === "strong") {
    return "Face found consistently. Face crop is likely to work well.";
  }
  const rawFaceFrames = typeof metadata?.raw_face_frames === "number" ? metadata.raw_face_frames : 0;
  const reliableFaceFrames = typeof metadata?.reliable_face_frames === "number" ? metadata.reliable_face_frames : 0;
  const filterReasonCounts = metadata?.filter_reason_counts || null;
  const tooSmall = typeof filterReasonCounts?.too_small === "number" ? filterReasonCounts.too_small : 0;
  const lowConfidence = typeof filterReasonCounts?.low_confidence === "number" ? filterReasonCounts.low_confidence : 0;
  if (rawFaceFrames > 0 && reliableFaceFrames === 0 && tooSmall > 0 && tooSmall >= lowConfidence) {
    return "Faces were detected but mostly filtered out as too small.";
  }
  if (rawFaceFrames > 0) {
    return "Face found, but framing confidence is low.";
  }
  return "No faces detected in sampled frames.";
}

function getFallbackCropNote(
  framingModeOverride: FramingModeOverride,
  metadata?: DraftClip["framing_metadata_json"],
): string {
  const fallbackPosition = formatFallbackCropPosition(metadata?.fallback_crop_position);
  if (framingModeOverride === "fixed_position") {
    return `Preview note: this clip will render with fixed ${fallbackPosition} fallback crop.`;
  }
  if (metadata?.suggested_crop_mode === "center" || getFramingStrength(metadata) === "none") {
    return `Preview note: this clip is likely to use ${fallbackPosition} fallback crop.`;
  }
  return "Preview note: this clip is likely to use face-aware crop tracking.";
}

function getFramingWarnings(metadata?: DraftClip["framing_metadata_json"]): string[] {
  const warnings: string[] = [];
  const rawFaceFrames = typeof metadata?.raw_face_frames === "number" ? metadata.raw_face_frames : 0;
  const reliableFaceFrames = typeof metadata?.reliable_face_frames === "number" ? metadata.reliable_face_frames : 0;
  const filterReasonCounts = metadata?.filter_reason_counts || null;
  const tooSmall = typeof filterReasonCounts?.too_small === "number" ? filterReasonCounts.too_small : 0;
  if (rawFaceFrames === 0) {
    warnings.push("No faces detected in sampled frames");
  } else if (reliableFaceFrames === 0 && tooSmall > 0) {
    warnings.push("Faces mostly filtered out as too small");
  }
  if (typeof metadata?.dominant_face_count === "number" && metadata.dominant_face_count > 1) {
    warnings.push("Multiple competing faces");
  }
  if (typeof metadata?.primary_face_area_ratio === "number" && metadata.primary_face_area_ratio > 0 && metadata.primary_face_area_ratio < 0.012) {
    warnings.push("Face appears small in frame");
  }
  if ((rawFaceFrames > 0 || Boolean(metadata?.face_detected)) && String(metadata?.crop_confidence || "none") === "low") {
    warnings.push("Detection confidence is low");
  }
  return warnings;
}

type StageKey = "download" | "transcript" | "analysis" | "clips" | "finalizing";

const STAGE_LABELS: Record<StageKey, string> = {
  download: "Download",
  transcript: "Transcript",
  analysis: "AI Analysis",
  clips: "Clip Creation",
  finalizing: "Finalizing",
};

const EMPTY_STAGE_PROGRESS: Record<StageKey, number> = {
  download: 0,
  transcript: 0,
  analysis: 0,
  clips: 0,
  finalizing: 0,
};

const EMPTY_STAGE_NOTES: Record<StageKey, string> = {
  download: "",
  transcript: "",
  analysis: "",
  clips: "",
  finalizing: "",
};

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function formatSeconds(value?: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "0.0s";
  }
  return `${value.toFixed(1)}s`;
}

function parseTimestampToSeconds(value: string): number {
  const normalized = (value || "").trim();
  if (!normalized) return 0;
  const parts = normalized.split(":");
  if (parts.length === 2) {
    const minutes = Number(parts[0]);
    const seconds = Number(parts[1]);
    if (!Number.isFinite(minutes) || !Number.isFinite(seconds)) return 0;
    return minutes * 60 + seconds;
  }
  if (parts.length === 3) {
    const hours = Number(parts[0]);
    const minutes = Number(parts[1]);
    const seconds = Number(parts[2]);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !Number.isFinite(seconds)) return 0;
    return hours * 3600 + minutes * 60 + seconds;
  }
  const raw = Number(normalized);
  return Number.isFinite(raw) ? raw : 0;
}

function computeDraftOverlapConflicts(drafts: DraftClip[]): DraftOverlapConflict[] {
  const orderedDrafts = [...drafts].sort((a, b) => {
    const startDiff = parseTimestampToSeconds(a.start_time) - parseTimestampToSeconds(b.start_time);
    if (Math.abs(startDiff) > 1e-6) {
      return startDiff;
    }
    return a.clip_order - b.clip_order;
  });

  const labeledDrafts = orderedDrafts.map((draft, index) => ({
    ...draft,
    displayLabel: `Clip ${index + 1} (${draft.start_time} -> ${draft.end_time})`,
    startSeconds: parseTimestampToSeconds(draft.start_time),
    endSeconds: parseTimestampToSeconds(draft.end_time),
  }));

  const conflicts: DraftOverlapConflict[] = [];
  for (let index = 1; index < labeledDrafts.length; index += 1) {
    const previous = labeledDrafts[index - 1];
    const current = labeledDrafts[index];
    if (current.startSeconds < previous.endSeconds - 1e-6) {
      conflicts.push({
        left_id: previous.id,
        right_id: current.id,
        left_label: previous.displayLabel,
        right_label: current.displayLabel,
        left_start_time: previous.start_time,
        left_end_time: previous.end_time,
        right_start_time: current.start_time,
        right_end_time: current.end_time,
      });
    }
  }

  return conflicts;
}

function deriveStageProgress(
  overallProgress: number,
  progressMessage: string,
  current: Record<StageKey, number>
): Record<StageKey, number> {
  const next = { ...current };
  const overall = clampPercent(overallProgress);
  const message = progressMessage.toLowerCase();

  if (message.includes("download")) {
    const match = progressMessage.match(/(\d{1,3})%/);
    if (match) {
      next.download = Math.max(next.download, clampPercent(Number(match[1])));
    }
  }

  if (overall >= 30) next.download = Math.max(next.download, 100);
  if (overall >= 50) next.transcript = Math.max(next.transcript, 100);
  if (overall >= 70) next.analysis = Math.max(next.analysis, 100);
  if (overall >= 95) next.clips = Math.max(next.clips, 100);
  if (overall >= 100) next.finalizing = 100;

  return next;
}

function getChunkStageProgress(metadata: TaskProgressMetadata): number | null {
  if (
    metadata.mode !== "chunked" ||
    typeof metadata.chunk_total !== "number" ||
    metadata.chunk_total <= 0
  ) {
    return null;
  }

  return clampPercent(
    ((metadata.chunks_completed ?? 0) / metadata.chunk_total) * 100
  );
}

function deriveStageNotesFromMessage(
  message: string,
  sourceType?: string
): Partial<Record<StageKey, string>> {
  const notes: Partial<Record<StageKey, string>> = {};
  const lower = (message || "").toLowerCase();

  if (lower.includes("found existing download") || lower.includes("skipping download")) {
    notes.download = "previous download found";
  }

  if (lower.includes("found existing transcript") || lower.includes("skipping transcription")) {
    notes.transcript = "previous transcript found";
    // If transcript is cached for YouTube, download was necessarily reused too.
    if (sourceType === "youtube") {
      notes.download = "previous download found";
    }
  }

  return notes;
}

function formatRetryStageLabel(stage: string): string {
  if (stage === "review_approved") {
    return "approved drafts";
  }
  return stage.replace(/_/g, " ");
}

export default function TaskPage() {
  const params = useParams();
  const router = useRouter();
  const { data: session, isPending } = useSession();
  const [task, setTask] = useState<TaskDetails | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [draftClips, setDraftClips] = useState<DraftClip[]>([]);
  const [draftsDirty, setDraftsDirty] = useState(false);
  const [isSavingDrafts, setIsSavingDrafts] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isRetryingTask, setIsRetryingTask] = useState(false);
  const [framingFilter, setFramingFilter] = useState<FramingFilter>("all");
  const [sourceVideoUrl, setSourceVideoUrl] = useState<string | null>(null);
  const [timelineEditorEnabled, setTimelineEditorEnabled] = useState(true);
  const [isUpdatingTaskOptions, setIsUpdatingTaskOptions] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [activeDraftClipId, setActiveDraftClipId] = useState<string | null>(null);
  const [expandedDraftClipId, setExpandedDraftClipId] = useState<string | null>(null);
  const [reviewMobileTab, setReviewMobileTab] = useState<"preview" | "clips">("preview");
  const [timelineZoomLevel, setTimelineZoomLevel] = useState<TimelineZoomLevel>(1);
  const [reasoningExpandedByClipId, setReasoningExpandedByClipId] = useState<Record<string, boolean>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [stageProgress, setStageProgress] = useState<Record<StageKey, number>>(EMPTY_STAGE_PROGRESS);
  const [stageNotes, setStageNotes] = useState<Record<StageKey, string>>(EMPTY_STAGE_NOTES);
  const [transcriptProgress, setTranscriptProgress] = useState<TranscriptProgressMetadata | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deletingClipId, setDeletingClipId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const draftClipRowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const progressRef = useRef(progress);
  const progressMessageRef = useRef(progressMessage);
  const sourceTypeRef = useRef<string | undefined>(task?.source_type);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const workflowLabel = useMemo(() => (task ? getTaskWorkflowLabel(task) : null), [task]);
  const taskId = Array.isArray(params.id) ? params.id[0] : params.id;
  const userId = session?.user?.id;
  const sortDraftClips = useCallback((drafts: DraftClip[]) => {
    return [...drafts].sort((a, b) => {
      const startDiff = parseTimestampToSeconds(a.start_time) - parseTimestampToSeconds(b.start_time);
      if (Math.abs(startDiff) > 1e-6) {
        return startDiff;
      }
      return a.clip_order - b.clip_order;
    });
  }, []);
  const overlapConflicts = useMemo(() => computeDraftOverlapConflicts(draftClips), [draftClips]);
  const conflictingDraftIds = useMemo(() => {
    const ids = new Set<string>();
    overlapConflicts.forEach((conflict) => {
      ids.add(conflict.left_id);
      ids.add(conflict.right_id);
    });
    return ids;
  }, [overlapConflicts]);
  const hasOverlapConflicts = overlapConflicts.length > 0;
  const retryableStages = task?.retryable_from_stages || [];
  const isDownloadFailure = task?.failure_code === "download";
  const isTranscriptionFailure = task?.failure_code === "transcription";
  const technicalErrorDetails = useMemo(() => {
    const rawMessage = typeof task?.progress_message === "string" ? task.progress_message.trim() : "";
    const hint = typeof task?.failure_hint === "string" ? task.failure_hint.trim() : "";
    if (!rawMessage || rawMessage === hint) {
      return null;
    }
    if (task?.failure_code === "download") {
      return rawMessage;
    }
    if (rawMessage.length > 240 || rawMessage.includes("/")) {
      return null;
    }
    return rawMessage;
  }, [task?.failure_code, task?.failure_hint, task?.progress_message]);

  const extractTaskApiErrorMessage = useCallback((payload: unknown, fallback: string): string => {
    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof (payload as { detail?: unknown }).detail === "object" &&
      (payload as { detail?: { message?: unknown } }).detail &&
      typeof (payload as { detail?: { message?: unknown } }).detail?.message === "string"
    ) {
      return (payload as { detail: { message: string } }).detail.message;
    }
    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof (payload as { detail?: unknown }).detail === "string"
    ) {
      return (payload as { detail: string }).detail;
    }
    return fallback;
  }, []);

  const registerDraftClipRowRef = useCallback((draftId: string, node: HTMLDivElement | null) => {
    if (node) {
      draftClipRowRefs.current[draftId] = node;
      return;
    }
    delete draftClipRowRefs.current[draftId];
  }, []);

  const focusDraftClip = useCallback(
    (
      draftId: string,
      options?: {
        expand?: boolean;
        scroll?: boolean;
        switchToClipsTab?: boolean;
      },
    ) => {
      setActiveDraftClipId(draftId);
      if (options?.expand !== false) {
        setExpandedDraftClipId(draftId);
      }
      if (options?.switchToClipsTab) {
        setReviewMobileTab("clips");
      }
      if (options?.scroll === false) {
        return;
      }
      window.requestAnimationFrame(() => {
        draftClipRowRefs.current[draftId]?.scrollIntoView({
          block: "nearest",
          behavior: "smooth",
        });
      });
    },
    [],
  );

  const toggleDraftClipExpansion = useCallback((draftId: string) => {
    setActiveDraftClipId(draftId);
    setExpandedDraftClipId((prev) => (prev === draftId ? null : draftId));
  }, []);

  const toggleReasoningVisibility = useCallback((draftId: string) => {
    setReasoningExpandedByClipId((prev) => ({
      ...prev,
      [draftId]: !prev[draftId],
    }));
  }, []);

  const getDraftDurationSeconds = useCallback((draft: DraftClip) => {
    const parsedDuration = parseTimestampToSeconds(draft.end_time) - parseTimestampToSeconds(draft.start_time);
    if (Number.isFinite(parsedDuration) && parsedDuration > 0) {
      return parsedDuration;
    }
    return Math.max(0, draft.duration || 0);
  }, []);

  useEffect(() => {
    progressRef.current = progress;
  }, [progress]);

  useEffect(() => {
    progressMessageRef.current = progressMessage;
  }, [progressMessage]);

  useEffect(() => {
    sourceTypeRef.current = task?.source_type;
  }, [task?.source_type]);

  useEffect(() => {
    setNowMs(Date.now());
    if (!task?.status || (task.status !== "queued" && task.status !== "processing" && task.status !== "awaiting_review")) {
      return;
    }
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [task?.status]);

  useEffect(() => {
    if (!timelineEditorEnabled && reviewMobileTab === "preview") {
      setReviewMobileTab("clips");
    }
  }, [reviewMobileTab, timelineEditorEnabled]);

  useEffect(() => {
    if (draftClips.length === 0) {
      if (activeDraftClipId !== null) {
        setActiveDraftClipId(null);
      }
      if (expandedDraftClipId !== null) {
        setExpandedDraftClipId(null);
      }
      return;
    }

    const draftIds = new Set(draftClips.map((draft) => draft.id));
    let nextActiveDraftId = activeDraftClipId;
    if (!nextActiveDraftId || !draftIds.has(nextActiveDraftId)) {
      nextActiveDraftId = draftClips[0].id;
      setActiveDraftClipId(nextActiveDraftId);
    }
    if (expandedDraftClipId && !draftIds.has(expandedDraftClipId)) {
      setExpandedDraftClipId(nextActiveDraftId);
    } else if (!expandedDraftClipId && activeDraftClipId === null) {
      setExpandedDraftClipId(nextActiveDraftId);
    }

    for (const existingId of Object.keys(draftClipRowRefs.current)) {
      if (!draftIds.has(existingId)) {
        delete draftClipRowRefs.current[existingId];
      }
    }
  }, [activeDraftClipId, draftClips, expandedDraftClipId]);

  const fetchTaskStatus = useCallback(async (retryCount = 0, maxRetries = 5) => {
    if (!taskId || !userId) return false;

    try {
      const headers: HeadersInit = {
        user_id: userId,
      };

      const taskResponse = await fetch(`${apiUrl}/tasks/${taskId}`, {
        headers,
      });

      // Handle 404 with retry logic (task might not be persisted yet)
      if (taskResponse.status === 404 && retryCount < maxRetries) {
        console.log(`Task not found yet, retrying in ${(retryCount + 1) * 500}ms... (${retryCount + 1}/${maxRetries})`);
        await new Promise((resolve) => setTimeout(resolve, (retryCount + 1) * 500));
        return fetchTaskStatus(retryCount + 1, maxRetries);
      }

      if (!taskResponse.ok) {
        throw new Error(`Failed to fetch task: ${taskResponse.status}`);
      }

      const taskData = await taskResponse.json();
      setTask(taskData);
      setTimelineEditorEnabled(
        typeof taskData.timeline_editor_enabled === "boolean" ? taskData.timeline_editor_enabled : true,
      );
      const nextProgress = taskData.progress ?? 0;
      const nextMessage = taskData.progress_message ?? "";
      setProgress(nextProgress);
      setProgressMessage(nextMessage);
      setStageProgress((prev) => deriveStageProgress(nextProgress, nextMessage, prev));
      const inferredNotes = deriveStageNotesFromMessage(nextMessage, taskData?.source_type);
      if (Object.keys(inferredNotes).length > 0) {
        setStageNotes((prev) => ({ ...prev, ...inferredNotes }));
      }
      setError(null);

      // Only fetch clips if task is completed
      if (taskData.status === "completed") {
        const clipsResponse = await fetch(`${apiUrl}/tasks/${taskId}/clips`, {
          headers,
        });

        if (!clipsResponse.ok) {
          throw new Error(`Failed to fetch clips: ${clipsResponse.status}`);
        }

        const clipsData = await clipsResponse.json();
        setClips(clipsData.clips || []);
        setDraftClips([]);
        setDraftsDirty(false);
        setDraftError(null);
        setSourceVideoUrl(null);
      } else if (taskData.status === "awaiting_review") {
        const draftsResponse = await fetch(`${apiUrl}/tasks/${taskId}/draft-clips`, {
          headers,
        });

        if (!draftsResponse.ok) {
          throw new Error(`Failed to fetch draft clips: ${draftsResponse.status}`);
        }

        const draftsData = await draftsResponse.json();
        setDraftClips(sortDraftClips((draftsData.draft_clips || []) as DraftClip[]));
        setDraftsDirty(false);
        setDraftError(null);
        setClips([]);
        setSourceVideoUrl(`${apiUrl}/tasks/${taskId}/source-video?user_id=${encodeURIComponent(userId)}`);
      } else {
        setClips([]);
        setDraftClips([]);
        setDraftsDirty(false);
        setDraftError(null);
        setSourceVideoUrl(null);
      }

      return true;
    } catch (err) {
      console.error("Error fetching task data:", err);
      setError(err instanceof Error ? err.message : "Failed to load task");
      return false;
    }
  }, [apiUrl, sortDraftClips, taskId, userId]);

  // Initial fetch
  useEffect(() => {
    if (!taskId || !userId) {
      setIsLoading(false);
      return;
    }

    const fetchTaskData = async () => {
      try {
        setIsLoading(true);
        await fetchTaskStatus();
      } finally {
        setIsLoading(false);
      }
    };

    fetchTaskData();
  }, [fetchTaskStatus, taskId, userId]);

  // Poll task status while queued/processing.
  useEffect(() => {
    if (!taskId || !userId || !task?.status) return;
    if (task.status !== "queued" && task.status !== "processing") return;

    const intervalId = window.setInterval(() => {
      fetchTaskStatus();
    }, 2000);

    // Trigger one immediate refresh when polling starts.
    fetchTaskStatus();

    return () => {
      window.clearInterval(intervalId);
    };
  }, [fetchTaskStatus, task?.status, taskId, userId]);

  // Subscribe to backend SSE progress stream for real-time updates.
  useEffect(() => {
    if (!taskId || !userId || !task?.status) return;
    if (task.status !== "queued" && task.status !== "processing") return;

    const progressUrl = `${apiUrl}/tasks/${taskId}/progress?user_id=${encodeURIComponent(userId)}`;
    const eventSource = new EventSource(progressUrl);

    const handleStatusOrProgress = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        if (typeof data.progress === "number") setProgress(data.progress);
        if (typeof data.message === "string") setProgressMessage(data.message);
        if (typeof data.message === "string") {
          const inferredNotes = deriveStageNotesFromMessage(data.message, sourceTypeRef.current);
          if (Object.keys(inferredNotes).length > 0) {
            setStageNotes((prev) => ({ ...prev, ...inferredNotes }));
          }
        }
        const metadata = (data?.metadata ?? {}) as TaskProgressMetadata;
        if (metadata.stage && metadata.stage in STAGE_LABELS) {
          const chunkStageProgress = getChunkStageProgress(metadata);
          const resolvedStageProgress =
            metadata.stage === "transcript" && chunkStageProgress !== null
              ? chunkStageProgress
              : clampPercent(metadata.stage_progress ?? 0);
          setStageProgress((prev) => ({
            ...prev,
            [metadata.stage as StageKey]:
              metadata.stage === "transcript" && chunkStageProgress !== null
                ? resolvedStageProgress
                : Math.max(prev[metadata.stage as StageKey], resolvedStageProgress),
          }));
          if (metadata.cached) {
            setStageNotes((prev) => {
              const note =
                metadata.stage === "download"
                  ? "previous download found"
                  : metadata.stage === "transcript"
                    ? "previous transcript found"
                    : "cached";
              return { ...prev, [metadata.stage as StageKey]: note };
            });
          }
          if (metadata.stage === "clips" && typeof metadata.stage_label === "string" && metadata.stage_label.trim()) {
            setStageNotes((prev) => ({
              ...prev,
              clips: metadata.stage_label as string,
            }));
          }
          if (metadata.stage === "transcript") {
            const hasChunkData =
              metadata.mode ||
              typeof metadata.chunk_total === "number" ||
              typeof metadata.chunk_index === "number" ||
              typeof metadata.chunks_completed === "number";

            if (hasChunkData) {
              setTranscriptProgress((prev) => ({
                mode: metadata.mode ?? prev?.mode,
                chunk_index:
                  typeof metadata.chunk_index === "number"
                    ? metadata.chunk_index
                    : prev?.chunk_index,
                chunk_total:
                  typeof metadata.chunk_total === "number"
                    ? metadata.chunk_total
                    : prev?.chunk_total,
                chunks_completed:
                  typeof metadata.chunks_completed === "number"
                    ? metadata.chunks_completed
                    : prev?.chunks_completed,
                chunk_start_seconds:
                  typeof metadata.chunk_start_seconds === "number"
                    ? metadata.chunk_start_seconds
                    : prev?.chunk_start_seconds,
                chunk_end_seconds:
                  typeof metadata.chunk_end_seconds === "number"
                    ? metadata.chunk_end_seconds
                    : prev?.chunk_end_seconds,
                chunk_elapsed_seconds:
                  typeof metadata.chunk_elapsed_seconds === "number"
                    ? metadata.chunk_elapsed_seconds
                    : prev?.chunk_elapsed_seconds,
                total_elapsed_seconds:
                  typeof metadata.total_elapsed_seconds === "number"
                    ? metadata.total_elapsed_seconds
                    : prev?.total_elapsed_seconds,
                average_chunk_seconds:
                  typeof metadata.average_chunk_seconds === "number"
                    ? metadata.average_chunk_seconds
                    : prev?.average_chunk_seconds,
              }));
              if (
                metadata.mode === "chunked" &&
                typeof metadata.chunks_completed === "number" &&
                typeof metadata.chunk_total === "number"
              ) {
                setStageNotes((prev) => ({
                  ...prev,
                  transcript: `chunk ${metadata.chunks_completed}/${metadata.chunk_total}`,
                }));
              } else if (metadata.mode === "single") {
                setStageNotes((prev) => ({
                  ...prev,
                  transcript: "single pass",
                }));
              }
            }
          }
        } else {
          const nextProgress = typeof data.progress === "number" ? data.progress : progressRef.current;
          const nextMessage = typeof data.message === "string" ? data.message : progressMessageRef.current;
          setStageProgress((prev) => deriveStageProgress(nextProgress, nextMessage, prev));
        }
        if (typeof data.status === "string") {
          setTask((prev) => (prev ? { ...prev, status: data.status } : prev));
        }
      } catch (err) {
        console.error("Failed to parse progress event:", err);
      }
    };

    const handleClose = () => {
      eventSource.close();
      // Refresh once when stream closes to fetch final task/clips state.
      fetchTaskStatus();
    };

    eventSource.addEventListener("status", handleStatusOrProgress);
    eventSource.addEventListener("progress", handleStatusOrProgress);
    eventSource.addEventListener("close", handleClose);
    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.removeEventListener("status", handleStatusOrProgress);
      eventSource.removeEventListener("progress", handleStatusOrProgress);
      eventSource.removeEventListener("close", handleClose);
      eventSource.close();
    };
  }, [apiUrl, fetchTaskStatus, task?.status, taskId, userId]);

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.8) {
      return "border border-emerald-200 bg-emerald-100 text-emerald-800 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200";
    }
    if (score >= 0.6) {
      return "border border-amber-200 bg-amber-100 text-amber-800 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200";
    }
    return "border border-rose-200 bg-rose-100 text-rose-800 dark:border-rose-500/40 dark:bg-rose-500/15 dark:text-rose-200";
  };

  const handleEditTitle = async () => {
    if (!editedTitle.trim() || !session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          user_id: session.user.id,
        },
        body: JSON.stringify({ title: editedTitle }),
      });

      if (response.ok) {
        setTask(task ? { ...task, source_title: editedTitle } : null);
        setIsEditing(false);
      } else {
        alert("Failed to update title");
      }
    } catch (err) {
      console.error("Error updating title:", err);
      alert("Failed to update title");
    }
  };

  const handleDeleteTask = async () => {
    if (!session?.user?.id || !params.id) return;

    setIsDeleting(true);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}`, {
        method: "DELETE",
        headers: {
          user_id: session.user.id,
        },
      });

      if (response.ok) {
        router.push("/list");
      } else {
        alert("Failed to delete task");
      }
    } catch (err) {
      console.error("Error deleting task:", err);
      alert("Failed to delete task");
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  const handleDeleteClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/clips/${clipId}`, {
        method: "DELETE",
        headers: {
          user_id: session.user.id,
        },
      });

      if (response.ok) {
        setClips(clips.filter((clip) => clip.id !== clipId));
        setDeletingClipId(null);
      } else {
        alert("Failed to delete clip");
      }
    } catch (err) {
      console.error("Error deleting clip:", err);
      alert("Failed to delete clip");
    }
  };

  const updateDraftClip = useCallback((draftId: string, patch: Partial<DraftClip>) => {
    setDraftClips((prev) =>
      sortDraftClips(prev.map((draft) => (draft.id === draftId ? { ...draft, ...patch } : draft)))
    );
    setDraftsDirty(true);
    setDraftError(null);
  }, [sortDraftClips]);

  const updateDraftClipTiming = useCallback(
    (draftId: string, startTime: string, endTime: string) => {
      updateDraftClip(draftId, { start_time: startTime, end_time: endTime });
    },
    [updateDraftClip],
  );

  const saveDraftClips = useCallback(
    async (options?: { force?: boolean; silent?: boolean }): Promise<boolean> => {
      if (!session?.user?.id || !params.id) return false;
      if (draftClips.length === 0) return true;
      if (!draftsDirty && !options?.force) return true;
      if (isSavingDrafts) return false;
      if (hasOverlapConflicts) {
        if (!options?.silent) {
          setDraftError("Resolve clip overlaps before saving or finalizing.");
        }
        return false;
      }

      setIsSavingDrafts(true);
      if (!options?.silent) {
        setDraftError(null);
      }
      try {
        const response = await fetch(`${apiUrl}/tasks/${params.id}/draft-clips`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session.user.id,
          },
          body: JSON.stringify({
            draft_clips: draftClips.map((draft) => ({
              id: draft.id,
              start_time: draft.start_time,
              end_time: draft.end_time,
              edited_text: draft.edited_text,
              is_selected: draft.is_selected,
              framing_mode_override: normalizeFramingModeOverride(draft.framing_mode_override),
            })),
          }),
        });

        if (!response.ok) {
          const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
          throw new Error(extractTaskApiErrorMessage(payload, `Failed to save drafts: ${response.status}`));
        }

        const payload = (await response.json()) as { draft_clips?: DraftClip[] };
        setDraftClips(sortDraftClips(payload.draft_clips || []));
        setDraftsDirty(false);
        return true;
      } catch (saveError) {
        const message =
          saveError instanceof Error ? saveError.message : "Failed to save draft clips.";
        setDraftError(message);
        return false;
      } finally {
        setIsSavingDrafts(false);
      }
    },
    [apiUrl, draftClips, draftsDirty, extractTaskApiErrorMessage, hasOverlapConflicts, isSavingDrafts, params.id, session?.user?.id, sortDraftClips],
  );

  useEffect(() => {
    if (
      !draftsDirty ||
      isSavingDrafts ||
      isFinalizing ||
      task?.status !== "awaiting_review" ||
      draftError ||
      hasOverlapConflicts
    ) {
      return;
    }
    const timeoutId = window.setTimeout(() => {
      void saveDraftClips({ silent: true });
    }, 700);
    return () => window.clearTimeout(timeoutId);
  }, [draftError, draftsDirty, hasOverlapConflicts, isFinalizing, isSavingDrafts, saveDraftClips, task?.status]);

  const handleCreateDraftClip = async (startTime: string, endTime: string): Promise<string | null> => {
    if (!session?.user?.id || !params.id) return null;

    setDraftError(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/draft-clips`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          user_id: session.user.id,
        },
        body: JSON.stringify({
          start_time: startTime,
          end_time: endTime,
          is_selected: true,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractTaskApiErrorMessage(payload, `Failed to create draft clip: ${response.status}`));
      }

      const payload = (await response.json()) as { draft_clip?: DraftClip };
      if (payload.draft_clip) {
        const createdDraft = payload.draft_clip as DraftClip;
        setDraftClips((prev) => sortDraftClips([...prev, createdDraft]));
        focusDraftClip(createdDraft.id, { expand: true, scroll: true });
        setReasoningExpandedByClipId((prev) => ({ ...prev, [createdDraft.id]: false }));
        setDraftsDirty(false);
        return createdDraft.id;
      } else {
        await fetchTaskStatus();
      }
      setDraftsDirty(false);
      return null;
    } catch (createError) {
      const message =
        createError instanceof Error ? createError.message : "Failed to create draft clip.";
      setDraftError(message);
      return null;
    }
  };

  const handleDeleteDraftClip = async (draftId: string) => {
    if (!session?.user?.id || !params.id) return;
    setDraftError(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/draft-clips/${draftId}`, {
        method: "DELETE",
        headers: {
          user_id: session.user.id,
        },
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(payload.detail || `Failed to delete draft clip: ${response.status}`);
      }

      const payload = (await response.json()) as { draft_clips?: DraftClip[] };
      setDraftClips(sortDraftClips(payload.draft_clips || []));
      setReasoningExpandedByClipId((prev) => {
        if (!(draftId in prev)) return prev;
        const next = { ...prev };
        delete next[draftId];
        return next;
      });
      setDraftsDirty(false);
    } catch (deleteError) {
      const message =
        deleteError instanceof Error ? deleteError.message : "Failed to delete draft clip.";
      setDraftError(message);
    }
  };

  const handleRestoreDrafts = async () => {
    if (!session?.user?.id || !params.id) return;
    setDraftError(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/draft-clips/restore`, {
        method: "POST",
        headers: {
          user_id: session.user.id,
        },
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractTaskApiErrorMessage(payload, `Failed to restore draft clips: ${response.status}`));
      }

      const payload = (await response.json()) as { draft_clips?: DraftClip[] };
      setDraftClips(sortDraftClips(payload.draft_clips || []));
      setDraftsDirty(false);
    } catch (restoreError) {
      const message =
        restoreError instanceof Error ? restoreError.message : "Failed to restore draft clips.";
      setDraftError(message);
    }
  };

  const handleToggleTimelineEditor = async (enabled: boolean) => {
    if (!session?.user?.id || !params.id || isUpdatingTaskOptions) return;
    setIsUpdatingTaskOptions(true);
    setDraftError(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          user_id: session.user.id,
        },
        body: JSON.stringify({
          timeline_editor_enabled: enabled,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: string };
        throw new Error(payload.detail || `Failed to update timeline option: ${response.status}`);
      }
      setTimelineEditorEnabled(enabled);
      setTask((prev) => (prev ? { ...prev, timeline_editor_enabled: enabled } : prev));
    } catch (toggleError) {
      const message =
        toggleError instanceof Error ? toggleError.message : "Failed to update timeline option.";
      setDraftError(message);
    } finally {
      setIsUpdatingTaskOptions(false);
    }
  };

  const handleFinalize = async () => {
    if (!session?.user?.id || !params.id || isFinalizing) return;
    if (hasOverlapConflicts) {
      setDraftError("Resolve clip overlaps before finalizing.");
      return;
    }
    if (draftsDirty) {
      const saved = await saveDraftClips({ force: true });
      if (!saved) return;
    }

    setIsFinalizing(true);
    setDraftError(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/finalize`, {
        method: "POST",
        headers: {
          user_id: session.user.id,
        },
      });

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(extractTaskApiErrorMessage(payload, `Failed to finalize task: ${response.status}`));
      }

      setTask((prev) =>
        prev
          ? {
              ...prev,
              status: "queued",
            }
          : prev
      );
      setProgress(0);
      setProgressMessage("Queued rendering from approved draft clips...");
      setStageProgress(EMPTY_STAGE_PROGRESS);
      setStageNotes(EMPTY_STAGE_NOTES);
      setTranscriptProgress(null);
      setDraftsDirty(false);
      await fetchTaskStatus();
    } catch (finalizeError) {
      const message =
        finalizeError instanceof Error ? finalizeError.message : "Failed to finalize task.";
      setDraftError(message);
    } finally {
      setIsFinalizing(false);
    }
  };

  const handleRetryTask = async (retryFromStage?: string) => {
    if (!session?.user?.id || !params.id) return;
    setIsRetryingTask(true);
    try {
      const response = await fetch(`${apiUrl}/tasks/${params.id}/retry`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          user_id: session.user.id,
        },
        body: JSON.stringify({
          retry_from_stage: retryFromStage,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(extractTaskApiErrorMessage(payload, "Failed to retry task"));
      }
      await fetchTaskStatus();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Failed to retry task");
    } finally {
      setIsRetryingTask(false);
    }
  };

  const displayProgressMessage = (() => {
    const msg = progressMessage || "";
    const lower = msg.toLowerCase();
    if (stageNotes.clips && progress >= 70 && progress < 100) {
      return stageNotes.clips;
    }
    if (lower.includes("found existing download") || lower.includes("skipping download")) {
      return "Processing video and generating clips...";
    }
    return msg;
  })();

  const getStageStatusLabel = (stage: StageKey): string => {
    if (stageNotes[stage]) {
      return stageNotes[stage];
    }

    // Fallback for cases where the cached transcript event was missed:
    // if download is cached and transcript is fully complete early in the pipeline,
    // treat transcript as cached for display purposes.
    if (
      stage === "transcript" &&
      stageProgress.transcript >= 100 &&
      stageNotes.download === "previous download found" &&
      progress < 70
    ) {
      return "previous transcript found";
    }

    // Mirror behavior for download if the transcript cache signal is present.
    if (
      stage === "download" &&
      stageProgress.download >= 100 &&
      stageNotes.transcript === "previous transcript found" &&
      (task?.source_type === "youtube")
    ) {
      return "previous download found";
    }

    return `${stageProgress[stage]}%`;
  };

  const transcriptChunkProgressPercent =
    transcriptProgress &&
    typeof transcriptProgress.chunk_total === "number" &&
    transcriptProgress.chunk_total > 0
      ? clampPercent(
          ((transcriptProgress.chunks_completed ?? 0) / transcriptProgress.chunk_total) * 100
        )
      : 0;

  const transcriptChunkWindowLabel =
    transcriptProgress &&
    typeof transcriptProgress.chunk_start_seconds === "number" &&
    typeof transcriptProgress.chunk_end_seconds === "number"
      ? `${transcriptProgress.chunk_start_seconds.toFixed(1)}s -> ${transcriptProgress.chunk_end_seconds.toFixed(1)}s`
      : null;
  const getDisplayedStageProgress = (stage: StageKey): number => {
    if (stage === "transcript" && transcriptProgress?.mode === "chunked") {
      return transcriptChunkProgressPercent;
    }
    return stageProgress[stage];
  };
  const selectedDraftCount = draftClips.filter((clip) => clip.is_selected).length;
  const selectedStrongFramingCount = draftClips.filter(
    (clip) => clip.is_selected && getFramingStrength(clip.framing_metadata_json) === "strong",
  ).length;
  const selectedWeakFramingCount = draftClips.filter(
    (clip) => clip.is_selected && getFramingStrength(clip.framing_metadata_json) === "weak",
  ).length;
  const selectedNoFaceCount = draftClips.filter(
    (clip) => clip.is_selected && getFramingStrength(clip.framing_metadata_json) === "none",
  ).length;
  const allDraftsMissingFaces =
    draftClips.length > 0 && draftClips.every((clip) => getFramingStrength(clip.framing_metadata_json) === "none");
  const visibleDraftClips = useMemo(() => {
    if (framingFilter === "best") {
      return draftClips.filter((clip) => getFramingStrength(clip.framing_metadata_json) === "strong");
    }
    if (framingFilter === "weak") {
      return draftClips.filter((clip) => getFramingStrength(clip.framing_metadata_json) === "weak");
    }
    if (framingFilter === "none") {
      return draftClips.filter((clip) => getFramingStrength(clip.framing_metadata_json) === "none");
    }
    return draftClips;
  }, [draftClips, framingFilter]);
  const autosaveStatus = isSavingDrafts
    ? "saving..."
    : hasOverlapConflicts
      ? "blocked by overlaps"
      : draftsDirty
        ? "pending changes"
        : "up to date";
  const autosaveStatusPillClass = isSavingDrafts
    ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200"
    : hasOverlapConflicts
      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-500/15 dark:text-red-200"
      : draftsDirty
        ? "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-500/40 dark:bg-orange-500/15 dark:text-orange-200"
        : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/15 dark:text-emerald-200";

  if (isPending) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6">
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid gap-6">
            {[1, 2].map((i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <Skeleton className="h-48 w-full mb-4" />
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <Alert>
            <AlertDescription>You need to sign in to view this task.</AlertDescription>
          </Alert>
          <Link href="/sign-in" className="mt-4 inline-block">
            <Button>Sign In</Button>
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6">
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <Skeleton className="h-48 w-full mb-4" />
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-white p-4">
        <div className="max-w-6xl mx-auto">
          <Alert>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Link href="/" className="mt-4 inline-block">
            <Button variant="outline">
              <ArrowLeft className="w-4 h-4" />
              Back to Home
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      {/* Header */}
      <div className="border-b bg-white">
        <div className="max-w-6xl mx-auto px-4 py-6">
          <div className="flex items-center gap-4 mb-4">
            <Link href="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4" />
                Back
              </Button>
            </Link>
          </div>

          {task && (
            <div>
              <div className="flex items-center gap-3 mb-2">
                {isEditing ? (
                  <div className="flex items-center gap-2 flex-1">
                    <Input
                      value={editedTitle}
                      onChange={(e) => setEditedTitle(e.target.value)}
                      className="text-2xl font-bold h-auto py-1"
                      autoFocus
                    />
                    <Button size="sm" onClick={handleEditTitle} disabled={!editedTitle.trim()}>
                      <Check className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setIsEditing(false);
                        setEditedTitle(task.source_title);
                      }}
                    >
                      <X className="w-4 h-4" />
                    </Button>
                  </div>
                ) : (
                  <>
                    <h1 className="text-2xl font-bold text-black">{task.source_title}</h1>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setIsEditing(true);
                        setEditedTitle(task.source_title);
                      }}
                    >
                      <Edit2 className="w-4 h-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={() => setShowDeleteDialog(true)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </>
                )}
              </div>
              <div className="flex items-center gap-4 text-sm text-gray-600">
                {task.source_url ? (
                  isHttpUrl(task.source_url) ? (
                    <a
                      href={task.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex max-w-[28rem]"
                      title={task.source_url}
                    >
                      <Badge variant="outline" className="max-w-full truncate normal-case">
                        {task.source_url}
                      </Badge>
                    </a>
                  ) : (
                    <Badge variant="outline" className="max-w-[28rem] truncate normal-case" title={task.source_url}>
                      {task.source_url}
                    </Badge>
                  )
                ) : (
                  <Badge variant="outline" className="normal-case">
                    {formatSourceTypeLabel(task.source_type)}
                  </Badge>
                )}
                <span className="flex items-center gap-1">
                  <Clock className="w-4 h-4" />
                  {new Date(task.created_at).toLocaleDateString()}
                </span>
                {(() => {
                  const runtimeSummary = getTaskRuntimeSummary(
                    task.created_at,
                    task.updated_at,
                    task.status,
                    task.runtime_info,
                    nowMs,
                  );
                  return (
                    <>
                      <span className="flex items-center gap-1">
                        <Timer className="w-4 h-4" />
                        Process {runtimeSummary.processing}
                      </span>
                      {runtimeSummary.reviewWait ? (
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" />
                          Review wait {runtimeSummary.reviewWait}
                        </span>
                      ) : null}
                    </>
                  );
                })()}
                {task.status === "completed" ? (
                  <span>
                    {clips.length} {clips.length === 1 ? "clip" : "clips"} generated
                  </span>
                ) : task.status === "processing" ? (
                  <Badge className="bg-emerald-100 text-emerald-800">Processing</Badge>
                ) : task.status === "queued" ? (
                  <Badge className="bg-yellow-100 text-yellow-800">Queued</Badge>
                ) : task.status === "awaiting_review" ? (
                  <Badge className="bg-amber-100 text-amber-800">Needs Review</Badge>
                ) : (
                  <Badge variant="outline" className="capitalize">
                    {task.status}
                  </Badge>
                )}
              </div>
              {task.ai_focus_tags && task.ai_focus_tags.length > 0 ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-gray-500">AI Focus</span>
                  {task.ai_focus_tags.map((tag) => (
                    <Badge key={tag} variant="outline" className="bg-white">
                      {formatAiFocusTag(tag)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-6xl mx-auto px-4 py-8">
        {task ? (
          <Card className="mb-6 border-slate-200 bg-slate-50/80 dark:border-slate-700 dark:bg-slate-900/70">
            <CardContent className="space-y-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Task Diagnostics</h3>
                {workflowLabel ? (
                  <Badge variant="outline" className="bg-white dark:bg-slate-950">
                    Workflow {workflowLabel}
                  </Badge>
                ) : null}
              </div>
              <div className="grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
                <div>
                  <p className="text-slate-500">Queue target</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{task.diagnostics?.queue_target || "n/a"}</p>
                </div>
                <div>
                  <p className="text-slate-500">Worker type</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{task.diagnostics?.worker_type || "n/a"}</p>
                </div>
                <div>
                  <p className="text-slate-500">Transcription</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">
                    {task.diagnostics?.transcription?.provider || task.transcription_provider || "n/a"}
                    {task.diagnostics?.transcription?.model ? ` / ${task.diagnostics.transcription.model}` : ""}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Runtime target</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{task.diagnostics?.runtime_target || "n/a"}</p>
                </div>
                <div>
                  <p className="text-slate-500">AI provider</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">
                    {task.diagnostics?.ai?.provider || task.ai_provider || "n/a"}
                    {task.diagnostics?.ai?.model ? ` / ${task.diagnostics.ai.model}` : ""}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Stage checkpoint</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{task.stage_checkpoint || "n/a"}</p>
                </div>
                <div>
                  <p className="text-slate-500">Current stage</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">{task.diagnostics?.current_stage || "n/a"}</p>
                </div>
                <div>
                  <p className="text-slate-500">Fallback reason</p>
                  <p className="font-medium text-slate-900 dark:text-slate-100">
                    {task.diagnostics?.fallback_reason || task.failure_hint || "None"}
                  </p>
                </div>
              </div>
              {task.progress_message ? (
                <p className="text-xs text-slate-600 dark:text-slate-300">{task.progress_message}</p>
              ) : null}
            </CardContent>
          </Card>
        ) : null}
        {task?.status === "processing" || task?.status === "queued" || !task ? (
          <div className="space-y-6">
            <div className="text-center mb-8">
              <h2 className="text-xl font-semibold text-foreground mb-2">
                {!task ? "Initializing..." : task.status === "queued" ? "Queued for Processing" : "Processing Video"}
              </h2>
              <p className="text-muted-foreground">
                {!task
                  ? "Setting up your task. This should only take a moment..."
                  : task.status === "queued"
                    ? "Your task is in the queue and will start processing shortly."
                    : "Generating clips from your video. This usually takes 2-3 minutes."}
              </p>
            </div>

            {/* Processing Status Display with Progress */}
            <Card className="mb-6">
              <CardContent className="p-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-center gap-3">
                    <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse"></div>
                    <p className="text-sm font-medium text-foreground">
                      {displayProgressMessage ||
                        (!task ? "Initializing your task..." : "Processing video and generating clips...")}
                    </p>
                  </div>

                  {/* Progress Bar */}
                  {progress > 0 && (
                    <div className="w-full">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs text-muted-foreground">Overall</span>
                        <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">{progress}%</span>
                      </div>
                      <div className="w-full bg-muted rounded-full h-2">
                        <div
                          className="bg-emerald-600 h-2 rounded-full transition-all duration-500 ease-out"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {progress > 0 && (
                    <div className="space-y-2">
                      {(Object.keys(STAGE_LABELS) as StageKey[]).map((stage) => (
                        <div key={stage} className="w-full">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-muted-foreground">{STAGE_LABELS[stage]}</span>
                            <span className="text-xs font-medium text-muted-foreground">
                              {getStageStatusLabel(stage)}
                            </span>
                          </div>
                          <div className="w-full bg-muted rounded-full h-1.5">
                            <div
                              className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500 ease-out"
                              style={{ width: `${getDisplayedStageProgress(stage)}%` }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {transcriptProgress && (
                    <div className="rounded-md border border-sky-300/70 bg-sky-50 p-3 space-y-2 dark:border-sky-700/60 dark:bg-sky-950/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-sky-900 dark:text-sky-100">Transcript Runtime</span>
                        <span className="text-xs text-sky-700 dark:text-sky-200">
                          {transcriptProgress.mode === "chunked" ? "Chunked Whisper" : "Single-pass Whisper"}
                        </span>
                      </div>

                      {transcriptProgress.mode === "chunked" && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-xs text-sky-800 dark:text-sky-100">
                            <span>
                              Chunks: {transcriptProgress.chunks_completed ?? 0}/
                              {transcriptProgress.chunk_total ?? 0}
                            </span>
                            <span>{transcriptChunkProgressPercent}%</span>
                          </div>
                          <div className="w-full bg-sky-200 rounded-full h-1.5 dark:bg-sky-900/80">
                            <div
                              className="bg-blue-600 h-1.5 rounded-full transition-all duration-500 ease-out dark:bg-blue-400"
                              style={{ width: `${transcriptChunkProgressPercent}%` }}
                            />
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-1 gap-1 text-xs text-sky-800 sm:grid-cols-2 dark:text-sky-100">
                        <span>
                          Current chunk:{" "}
                          {typeof transcriptProgress.chunk_index === "number" &&
                          typeof transcriptProgress.chunk_total === "number"
                            ? `${transcriptProgress.chunk_index}/${transcriptProgress.chunk_total}`
                            : "n/a"}
                        </span>
                        <span>Last chunk time: {formatSeconds(transcriptProgress.chunk_elapsed_seconds)}</span>
                        <span>Total transcript time: {formatSeconds(transcriptProgress.total_elapsed_seconds)}</span>
                        <span>Avg chunk time: {formatSeconds(transcriptProgress.average_chunk_seconds)}</span>
                      </div>
                      {transcriptChunkWindowLabel && (
                        <p className="text-xs text-sky-700 dark:text-sky-200">Chunk window: {transcriptChunkWindowLabel}</p>
                      )}
                    </div>
                  )}

                  <p className="text-xs text-muted-foreground text-center">
                    This page will automatically update when your clips are ready
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Skeleton for clips being generated */}
            {[1, 2].map((i) => (
              <Card key={i} className="overflow-hidden">
                <CardContent className="p-0">
                  <div className="flex flex-col lg:flex-row">
                    {/* Video Player Skeleton */}
                    <div className="bg-gray-200 relative flex-shrink-0 flex items-center justify-center w-full lg:w-96 h-48 lg:h-64">
                      <Skeleton className="w-full h-full" />
                    </div>

                    {/* Clip Details Skeleton */}
                    <div className="p-6 flex-1">
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <Skeleton className="h-6 w-24 mb-2" />
                          <Skeleton className="h-4 w-32" />
                        </div>
                        <Skeleton className="h-6 w-12" />
                      </div>

                      <div className="mb-4">
                        <Skeleton className="h-4 w-16 mb-2" />
                        <Skeleton className="h-20 w-full" />
                      </div>

                      <div className="mb-4">
                        <Skeleton className="h-4 w-20 mb-2" />
                        <Skeleton className="h-4 w-full mb-1" />
                        <Skeleton className="h-4 w-3/4" />
                      </div>

                      <Skeleton className="h-8 w-24" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : task?.status === "awaiting_review" ? (
          <div className="space-y-5">
            <Card className="sticky top-3 z-20 border-slate-200/90 bg-white/95 shadow-[0_8px_24px_-18px_rgba(15,23,42,0.55)] backdrop-blur supports-[backdrop-filter]:bg-white/80 dark:border-slate-700/90 dark:bg-slate-900/95 dark:shadow-[0_10px_26px_-20px_rgba(2,6,23,0.9)] dark:supports-[backdrop-filter]:bg-slate-900/85">
              <CardContent className="space-y-4 p-4 sm:p-5">
                <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                  <div>
                    <h2 className="text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Review Draft Clips</h2>
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      Trim timing, refine subtitles, and include only the clips you want rendered.
                    </p>
                    <div aria-live="polite" className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-medium text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200">
                        Included {selectedDraftCount}/{draftClips.length}
                      </span>
                      <span className={`rounded-full border px-2.5 py-1 font-medium ${autosaveStatusPillClass}`}>
                        Autosave {autosaveStatus}
                      </span>
                      <span className="rounded-full border border-green-200 bg-green-50 px-2.5 py-1 font-medium text-green-700 dark:border-green-500/40 dark:bg-green-500/15 dark:text-green-200">
                        Strong framing {selectedStrongFramingCount}
                      </span>
                      <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 font-medium text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/15 dark:text-amber-200">
                        Weak framing {selectedWeakFramingCount}
                      </span>
                      <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 font-medium text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200">
                        No face {selectedNoFaceCount}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                      onClick={() => void handleRestoreDrafts()}
                      disabled={isSavingDrafts || isFinalizing || draftClips.length === 0}
                    >
                      Restore
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                      onClick={() => void saveDraftClips()}
                      disabled={isSavingDrafts || isFinalizing || draftClips.length === 0 || hasOverlapConflicts}
                    >
                      {isSavingDrafts ? "Saving..." : draftsDirty ? "Save Now" : "Saved"}
                    </Button>
                    <Button
                      size="sm"
                      className="shadow-sm"
                      onClick={() => void handleFinalize()}
                      disabled={
                        isSavingDrafts ||
                        isFinalizing ||
                        draftClips.length === 0 ||
                        selectedDraftCount === 0 ||
                        hasOverlapConflicts
                      }
                    >
                      {isFinalizing ? "Finalizing..." : "Finalize & Render"}
                    </Button>
                  </div>
                </div>

                {hasOverlapConflicts ? (
                  <Alert className="border-red-300 bg-red-50 text-red-900 dark:border-red-800/70 dark:bg-red-950/30 dark:text-red-100">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription className="space-y-2">
                      <p className="font-medium">
                        Resolve {overlapConflicts.length} overlap{overlapConflicts.length === 1 ? "" : "s"} before saving or finalizing.
                      </p>
                      <div className="space-y-1 text-sm">
                        {overlapConflicts.map((conflict, index) => (
                          <div key={`${conflict.left_id}:${conflict.right_id}:${index}`}>
                            {conflict.left_label} overlaps {conflict.right_label}
                          </div>
                        ))}
                      </div>
                    </AlertDescription>
                  </Alert>
                ) : null}

                {allDraftsMissingFaces ? (
                  <Alert className="border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700/70 dark:bg-amber-950/30 dark:text-amber-100">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      No draft clips currently have a reliable face target. Fallback crop is still safe, but if the speaker is small or far from camera, switch Video settings to <span className="font-medium">More faces</span> or adjust the <span className="font-medium">Fallback crop position</span> and run the task again.
                    </AlertDescription>
                  </Alert>
                ) : null}

                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/70">
                    <label className="flex items-center gap-2 text-sm font-medium text-slate-900 dark:text-slate-100">
                      <input
                        type="checkbox"
                        checked={timelineEditorEnabled}
                        onChange={(event) => void handleToggleTimelineEditor(event.target.checked)}
                        disabled={isUpdatingTaskOptions || isSavingDrafts || isFinalizing}
                        className="h-4 w-4"
                      />
                      Interactive timeline editor
                    </label>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                      Drag clip boundaries with 0.5s snapping and no overlaps.
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/70">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">Framing Filter</p>
                    <div className="mt-2 w-full min-w-[13rem]">
                      <Select value={framingFilter} onValueChange={(value) => setFramingFilter(value as FramingFilter)}>
                        <SelectTrigger className="h-9 w-full bg-white dark:bg-slate-950">
                          <SelectValue placeholder="Filter framing" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All clips</SelectItem>
                          <SelectItem value="best">Best framing</SelectItem>
                          <SelectItem value="weak">Weak framing</SelectItem>
                          <SelectItem value="none">No face</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                      Framing badges are predictive. Final render can still differ slightly.
                    </p>
                  </div>

                  <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-slate-700 dark:bg-slate-800 lg:hidden">
                    <button
                      type="button"
                      className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                        reviewMobileTab === "preview"
                          ? "bg-slate-100 text-black shadow-sm dark:bg-slate-700 dark:text-slate-100"
                          : "text-slate-600 hover:text-black dark:text-slate-300 dark:hover:text-slate-100"
                      }`}
                      onClick={() => setReviewMobileTab("preview")}
                      disabled={!timelineEditorEnabled}
                    >
                      Preview
                    </button>
                    <button
                      type="button"
                      className={`rounded-md px-3 py-1.5 text-xs font-medium ${
                        reviewMobileTab === "clips"
                          ? "bg-slate-100 text-black shadow-sm dark:bg-slate-700 dark:text-slate-100"
                          : "text-slate-600 hover:text-black dark:text-slate-300 dark:hover:text-slate-100"
                      }`}
                      onClick={() => setReviewMobileTab("clips")}
                    >
                      Clips
                    </button>
                  </div>
                </div>

                {draftError && (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{draftError}</AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>

            <div className="grid gap-5 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:items-start">
              <div className={reviewMobileTab === "clips" ? "hidden lg:block" : ""}>
                {timelineEditorEnabled ? (
                  <div className="lg:sticky lg:top-32">
                    <DraftTimelineEditor
                      sourceVideoUrl={sourceVideoUrl}
                      drafts={draftClips}
                      conflictingClipIds={[...conflictingDraftIds]}
                      disabled={isSavingDrafts || isFinalizing}
                      selectedClipId={activeDraftClipId}
                      timelineZoomLevel={timelineZoomLevel}
                      onTimelineZoomLevelChange={setTimelineZoomLevel}
                      onSelectClip={(draftId) => focusDraftClip(draftId, { expand: true, scroll: true })}
                      onDraftTimingChange={updateDraftClipTiming}
                      onAddDraft={handleCreateDraftClip}
                    />
                  </div>
                ) : (
                  <Card className="border-slate-200 bg-slate-50/40 dark:border-slate-700 dark:bg-slate-900/70">
                    <CardContent className="p-6 text-center text-sm text-slate-600 dark:text-slate-300">
                      Timeline preview is disabled. Enable &quot;Interactive timeline editor&quot; to use drag-and-trim controls.
                    </CardContent>
                  </Card>
                )}
              </div>

              <div className={reviewMobileTab === "preview" ? "hidden lg:block" : ""}>
                {visibleDraftClips.length === 0 ? (
                  <Card className="border-slate-200 bg-slate-50/40 dark:border-slate-700 dark:bg-slate-900/70">
                    <CardContent className="p-6 text-center text-sm text-slate-600 dark:text-slate-300">
                      {draftClips.length === 0
                        ? `No draft clips are available for review.${timelineEditorEnabled ? " Use the timeline to add one at the playhead." : ""}`
                        : "No draft clips match the current framing filter."}
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-3 lg:max-h-[calc(100vh-12rem)] lg:overflow-y-auto lg:pr-1">
                    {visibleDraftClips.map((draft, displayIndex) => {
                      const isActive = activeDraftClipId === draft.id;
                      const isExpanded = expandedDraftClipId === draft.id;
                      const isReasoningVisible = Boolean(reasoningExpandedByClipId[draft.id]);
                      const reviewScore = typeof draft.review_score === "number" ? draft.review_score : draft.relevance_score;
                      const scoreAdjustment = typeof draft.feedback_score_adjustment === "number" ? draft.feedback_score_adjustment : 0;
                      const feedbackSignals = draft.feedback_signals_json || null;
                      const framingMetadata = draft.framing_metadata_json || null;
                      const framingWarnings = getFramingWarnings(framingMetadata);
                      const framingModeOverride = normalizeFramingModeOverride(draft.framing_mode_override);
                      const hasScoreAdjustment = Math.abs(scoreAdjustment) >= 0.005;
                      const isConflicting = conflictingDraftIds.has(draft.id);
                      return (
                        <div
                          key={draft.id}
                          ref={(node) => registerDraftClipRowRef(draft.id, node)}
                          className={`relative overflow-hidden rounded-xl border bg-white transition-all ${
                            isConflicting
                              ? "border-red-300 bg-red-50/50 shadow-[0_10px_20px_-16px_rgba(220,38,38,0.45)] dark:border-red-600/70 dark:bg-red-950/20"
                              : isActive
                              ? "border-blue-300 bg-blue-50/40 shadow-[0_10px_20px_-16px_rgba(37,99,235,0.6)] dark:border-blue-500/70 dark:bg-blue-950/30 dark:shadow-[0_12px_24px_-18px_rgba(30,64,175,0.9)]"
                              : "border-slate-200 hover:border-slate-300 hover:shadow-sm dark:border-slate-700 dark:bg-slate-900/70 dark:hover:border-slate-500"
                          }`}
                          aria-selected={isActive}
                        >
                          <div
                            className={`absolute inset-y-0 left-0 w-1 transition-colors ${
                              isConflicting ? "bg-red-500" : isActive ? "bg-blue-500" : "bg-transparent"
                            }`}
                            aria-hidden
                          />
                          <div className="flex items-center gap-3 px-4 py-3.5">
                            <input
                              type="checkbox"
                              checked={draft.is_selected}
                              onChange={(event) => {
                                focusDraftClip(draft.id, { expand: false, scroll: false });
                                updateDraftClip(draft.id, { is_selected: event.target.checked });
                              }}
                              disabled={isSavingDrafts || isFinalizing}
                              className="h-4 w-4"
                            />
                            <button
                              type="button"
                              className="min-w-0 flex-1 text-left"
                              onClick={() => toggleDraftClipExpansion(draft.id)}
                              aria-expanded={isExpanded}
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-semibold text-slate-900 dark:text-slate-100">Clip {displayIndex + 1}</h3>
                                <Badge className={getScoreColor(reviewScore)}>
                                  <Star className="mr-1 h-3 w-3" />
                                  {(reviewScore * 100).toFixed(0)}%
                                </Badge>
                                {hasScoreAdjustment ? (
                                  <Badge variant="outline">
                                    {scoreAdjustment > 0 ? "+" : ""}
                                    {(scoreAdjustment * 100).toFixed(0)}% review
                                  </Badge>
                                ) : null}
                                <Badge className={getFramingBadgeClass(framingMetadata)}>
                                  {getFramingBadgeLabel(framingMetadata)}
                                </Badge>
                                {isConflicting ? <Badge className="bg-red-100 text-red-800">Overlap</Badge> : null}
                                {typeof framingMetadata?.dominant_face_count === "number" && framingMetadata.dominant_face_count > 1 ? (
                                  <Badge variant="outline">Multiple faces</Badge>
                                ) : null}
                                {draft.created_by_user && <Badge variant="outline">Manual</Badge>}
                                {feedbackSignals?.timing_changed ? <Badge variant="outline">Retimed</Badge> : null}
                                {feedbackSignals?.text_edited ? <Badge variant="outline">Text Edited</Badge> : null}
                                {feedbackSignals?.deselected ? <Badge variant="outline">Deselected</Badge> : null}
                              </div>
                              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs">
                                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 font-medium text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200">
                                  {draft.start_time}
                                  {" -> "}
                                  {draft.end_time}
                                </span>
                                <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                  Duration {formatDuration(getDraftDurationSeconds(draft))}
                                </span>
                                {hasScoreAdjustment ? (
                                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-slate-600 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300">
                                    AI {(draft.relevance_score * 100).toFixed(0)}% {"->"} Review {(reviewScore * 100).toFixed(0)}%
                                  </span>
                                ) : null}
                              </div>
                            </button>

                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 border-slate-300 bg-slate-50 px-2 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                              onClick={() => toggleDraftClipExpansion(draft.id)}
                              disabled={isSavingDrafts || isFinalizing}
                            >
                              {isExpanded ? "Hide" : "Edit"}
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 border-red-200 px-2 text-xs text-red-600 hover:bg-red-50 hover:text-red-700"
                              onClick={() => void handleDeleteDraftClip(draft.id)}
                              disabled={isSavingDrafts || isFinalizing}
                            >
                              <Trash2 className="mr-1 h-3 w-3" />
                              Delete
                            </Button>
                          </div>

                          {isExpanded && (
                            <div className="space-y-3 border-t border-slate-200 bg-slate-50/60 px-4 py-3.5 dark:border-slate-700 dark:bg-slate-900/70">
                              {draft.preview_url ? (
                                <div className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-950/70">
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img
                                    src={`${apiUrl}${draft.preview_url}?user_id=${encodeURIComponent(userId || "")}`}
                                    alt={`Preview strip for clip ${displayIndex + 1}`}
                                    className="h-auto w-full object-cover"
                                  />
                                </div>
                              ) : null}

                              {draft.selection_rationale ? (
                                <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950/70">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant="outline">
                                      Transcript {(Number(draft.selection_rationale.transcript_relevance || 0) * 100).toFixed(0)}%
                                    </Badge>
                                    <Badge variant="outline">
                                      Hook {(Number(draft.selection_rationale.hook_score || 0) * 100).toFixed(0)}%
                                    </Badge>
                                    <Badge variant="outline">
                                      Framing {String(draft.selection_rationale.framing_quality || "none")}
                                    </Badge>
                                    {(draft.selection_rationale.review_adjustments || []).map((adjustment) => (
                                      <Badge key={adjustment} variant="outline">
                                        {adjustment}
                                      </Badge>
                                    ))}
                                  </div>
                                </div>
                              ) : null}

                              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 dark:border-slate-700 dark:bg-slate-950/70">
                                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                  <div className="space-y-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge className={getFramingBadgeClass(framingMetadata)}>
                                        {getFramingBadgeLabel(framingMetadata)}
                                      </Badge>
                                      {typeof framingMetadata?.face_detection_rate === "number" ? (
                                        <Badge variant="outline">
                                          Detection {(framingMetadata.face_detection_rate * 100).toFixed(0)}%
                                        </Badge>
                                      ) : null}
                                      {typeof framingMetadata?.primary_face_area_ratio === "number" ? (
                                        <Badge variant="outline">
                                          Face size {(framingMetadata.primary_face_area_ratio * 100).toFixed(1)}%
                                        </Badge>
                                      ) : null}
                                      {typeof framingMetadata?.sampled_frames === "number" && framingMetadata.sampled_frames > 0 ? (
                                        <Badge variant="outline">Samples {framingMetadata.sampled_frames}</Badge>
                                      ) : null}
                                      {typeof framingMetadata?.raw_face_frames === "number" && framingMetadata.raw_face_frames > 0 ? (
                                        <Badge variant="outline">
                                          Raw hits {framingMetadata.raw_face_frames}
                                          {typeof framingMetadata?.reliable_face_frames === "number"
                                            ? ` / Reliable ${framingMetadata.reliable_face_frames}`
                                            : ""}
                                        </Badge>
                                      ) : null}
                                      {typeof framingMetadata?.detector_backend === "string" &&
                                      framingMetadata.detector_backend &&
                                      framingMetadata.detector_backend !== "none" ? (
                                        <Badge variant="outline">Detector {framingMetadata.detector_backend}</Badge>
                                      ) : null}
                                    </div>
                                    <p className="text-xs text-slate-600 dark:text-slate-300">
                                      {getFramingExplanation(framingMetadata)}
                                    </p>
                                    {(framingModeOverride === "fixed_position" || framingMetadata?.suggested_crop_mode === "center") && (
                                      <p className="text-xs text-slate-500 dark:text-slate-400">
                                        Fallback crop: {formatFallbackCropPosition(framingMetadata?.fallback_crop_position)}
                                      </p>
                                    )}
                                    {framingWarnings.length > 0 ? (
                                      <div className="flex flex-wrap gap-2">
                                    {framingWarnings.map((warning) => (
                                          <Badge key={warning} variant="outline" className="border-amber-300 bg-amber-50 text-amber-800">
                                            {warning}
                                          </Badge>
                                        ))}
                                      </div>
                                    ) : null}
                                    {isConflicting ? (
                                      <p className="text-xs font-medium text-red-700 dark:text-red-300">
                                        This clip overlaps another draft. Adjust the highlighted timing to continue.
                                      </p>
                                    ) : null}
                                  </div>
                                  <div className="w-full max-w-[15rem] space-y-1">
                                    <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Crop Mode</label>
                                    <Select
                                      value={framingModeOverride}
                                      onValueChange={(value) =>
                                        updateDraftClip(draft.id, {
                                          framing_mode_override: normalizeFramingModeOverride(value),
                                        })
                                      }
                                      disabled={isSavingDrafts || isFinalizing}
                                    >
                                      <SelectTrigger className="h-9 bg-white dark:bg-slate-950">
                                        <SelectValue placeholder="Select crop mode" />
                                      </SelectTrigger>
                                      <SelectContent>
                                        <SelectItem value="auto">Auto</SelectItem>
                                        <SelectItem value="prefer_face">Prefer face</SelectItem>
                                        <SelectItem value="fixed_position">Fixed position</SelectItem>
                                      </SelectContent>
                                    </Select>
                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                      {getFallbackCropNote(framingModeOverride, framingMetadata)}
                                    </p>
                                  </div>
                                </div>
                              </div>

                              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                <div className="space-y-1">
                                  <label className="text-xs font-medium text-slate-700 dark:text-slate-300">
                                    Start (MM:SS or HH:MM:SS, .5 allowed)
                                  </label>
                                  <Input
                                    value={draft.start_time}
                                    onFocus={() => focusDraftClip(draft.id, { expand: true, scroll: false })}
                                    onChange={(event) =>
                                      updateDraftClip(draft.id, { start_time: event.target.value })
                                    }
                                    disabled={isSavingDrafts || isFinalizing}
                                  />
                                </div>
                                <div className="space-y-1">
                                  <label className="text-xs font-medium text-slate-700 dark:text-slate-300">
                                    End (MM:SS or HH:MM:SS, .5 allowed)
                                  </label>
                                  <Input
                                    value={draft.end_time}
                                    onFocus={() => focusDraftClip(draft.id, { expand: true, scroll: false })}
                                    onChange={(event) =>
                                      updateDraftClip(draft.id, { end_time: event.target.value })
                                    }
                                    disabled={isSavingDrafts || isFinalizing}
                                  />
                                </div>
                              </div>

                              <div className="space-y-1">
                                <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Edited Subtitle Text</label>
                                <textarea
                                  value={draft.edited_text ?? ""}
                                  onFocus={() => focusDraftClip(draft.id, { expand: true, scroll: false })}
                                  onChange={(event) =>
                                    updateDraftClip(draft.id, { edited_text: event.target.value })
                                  }
                                  disabled={isSavingDrafts || isFinalizing}
                                  className="w-full min-h-[96px] rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:border-slate-600 dark:bg-slate-950 dark:text-slate-100"
                                />
                              </div>

                              {draft.reasoning && (
                                <div className="space-y-2">
                                  <button
                                    type="button"
                                    className="text-xs font-medium text-slate-600 underline-offset-2 hover:text-black hover:underline dark:text-slate-300 dark:hover:text-slate-100"
                                    onClick={() => toggleReasoningVisibility(draft.id)}
                                  >
                                    {isReasoningVisible ? "Hide AI reasoning" : "Show AI reasoning"}
                                  </button>
                                  {isReasoningVisible && (
                                    <div className="rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300">
                                      <span className="font-medium text-slate-900 dark:text-slate-100">AI reasoning: </span>
                                      {draft.reasoning}
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : task?.status === "error" ? (
          <Card>
            <CardContent className="p-8 text-center">
              <div className="text-red-600 mb-4">
                <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                <h2 className="text-xl font-semibold">
                  {isDownloadFailure
                    ? "Video Download Failed"
                    : isTranscriptionFailure
                      ? "Transcription Failed"
                      : "Processing Failed"}
                </h2>
              </div>
              <p className="text-gray-600 mb-2">
                {isDownloadFailure
                  ? "We couldn't access the source video. YouTube likely asked for sign-in verification."
                  : isTranscriptionFailure
                    ? "We downloaded the video, but couldn't prepare a clean audio track for transcription."
                  : "There was an error processing your video."}
              </p>
              {task.failure_code ? (
                <p className="mb-2 text-sm font-medium text-red-700">Failure code: {task.failure_code}</p>
              ) : null}
              {task.failure_hint ? (
                <p className="mx-auto mb-4 max-w-2xl text-sm text-slate-600 dark:text-slate-300">{task.failure_hint}</p>
              ) : null}
              {isDownloadFailure ? (
                <div className="mb-4 flex justify-center">
                  <Link href="/settings?section=transcription">
                    <Button variant="outline">Open Transcription Settings</Button>
                  </Link>
                </div>
              ) : null}
              {technicalErrorDetails ? (
                <details className="mx-auto mb-4 max-w-2xl rounded border border-slate-200 bg-slate-50 p-3 text-left dark:border-slate-700 dark:bg-slate-900/50">
                  <summary className="cursor-pointer text-sm font-medium text-slate-800 dark:text-slate-200">
                    Technical details
                  </summary>
                  <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{technicalErrorDetails}</p>
                </details>
              ) : null}
              {retryableStages.length > 0 ? (
                <div className="mb-4 flex flex-wrap justify-center gap-2">
                  {retryableStages.map((stage) => (
                    <Button
                      key={stage}
                      variant="outline"
                      onClick={() => void handleRetryTask(stage)}
                      disabled={isRetryingTask}
                    >
                      Retry from {formatRetryStageLabel(stage)}
                    </Button>
                  ))}
                </div>
              ) : null}
              <Link href="/">
                <Button>
                  <ArrowLeft className="w-4 h-4" />
                  Back to Home
                </Button>
              </Link>
            </CardContent>
          </Card>
        ) : clips.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              {task?.status === "completed" ? (
                <>
                  <div className="text-yellow-600 mb-4">
                    <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                    <h2 className="text-xl font-semibold">No Clips Generated</h2>
                  </div>
                  <p className="text-gray-600 mb-4">
                    The task completed but no clips were generated. The video may not have had suitable content for
                    clipping.
                  </p>
                  {task?.progress_message && (
                    <p className="text-sm text-left text-gray-700 bg-gray-50 border border-gray-200 rounded p-3 mb-4 dark:text-gray-100 dark:bg-slate-800/70 dark:border-slate-700">
                      {task.progress_message}
                    </p>
                  )}
                  <Link href="/">
                    <Button>
                      <ArrowLeft className="w-4 h-4 mr-2" />
                      Try Another Video
                    </Button>
                  </Link>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Clock className="w-8 h-8 text-blue-500 animate-pulse" />
                  </div>
                  <h2 className="text-xl font-semibold text-black mb-2">Still Generating...</h2>
                  <p className="text-gray-600">
                    Your clips are being generated. This page will refresh automatically when they&apos;re ready.
                  </p>
                </>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6">
            {/* Font Settings Display */}
            {task && (
              <div className="bg-gray-50 rounded-lg p-4">
                <h3 className="text-sm font-medium text-black mb-3 flex items-center gap-2">
                  <span className="w-4 h-4">🎨</span>
                  Font Settings
                </h3>
                <div className="grid grid-cols-3 gap-4 text-xs">
                  <div>
                    <span className="text-gray-500">Font:</span>
                    <p className="font-medium">{task.font_family || "Default"}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Size:</span>
                    <p className="font-medium">{task.font_size || 24}px</p>
                  </div>
                  <div>
                    <span className="text-gray-500">Color:</span>
                    <div className="flex items-center gap-1">
                      <div
                        className="w-3 h-3 rounded border"
                        style={{ backgroundColor: task.font_color || "#FFFFFF" }}
                      ></div>
                      <p className="font-medium">{task.font_color || "#FFFFFF"}</p>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {clips.map((clip) => (
              <Card key={clip.id} className="overflow-hidden">
                <CardContent className="p-0">
                  <div className="flex flex-col lg:flex-row">
                    {/* Video Player */}
                    <div className="bg-black relative flex-shrink-0 flex items-center justify-center">
                      <DynamicVideoPlayer
                        src={`${apiUrl}${clip.video_url}`}
                        poster="/placeholder-video.jpg"
                      />
                    </div>

                    {/* Clip Details */}
                    <div className="p-6">
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <h3 className="font-semibold text-lg text-black mb-1">Clip {clip.clip_order}</h3>
                          <div className="flex items-center gap-2 text-sm text-gray-600">
                            <span>
                              {clip.start_time} - {clip.end_time}
                            </span>
                            <span>•</span>
                            <span>{formatDuration(clip.duration)}</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge className={getScoreColor(clip.relevance_score)}>
                            <Star className="w-3 h-3 mr-1" />
                            {(clip.relevance_score * 100).toFixed(0)}%
                          </Badge>
                        </div>
                      </div>

                      {clip.text && (
                        <div className="mb-4">
                          <h4 className="font-medium text-black mb-2">Transcript</h4>
                          <p className="text-sm text-gray-700 bg-gray-50 border border-gray-200 p-3 rounded leading-relaxed dark:text-gray-100 dark:bg-slate-800/70 dark:border-slate-700">
                            {clip.text}
                          </p>
                        </div>
                      )}

                      {clip.reasoning && (
                        <div className="mb-4">
                          <h4 className="font-medium text-black mb-2">AI Analysis</h4>
                          <p className="text-sm text-gray-600">{clip.reasoning}</p>
                        </div>
                      )}

                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" asChild>
                          <a href={`${apiUrl}${clip.video_url}`} download={clip.filename}>
                            <Download className="w-4 h-4 mr-2" />
                            Download
                          </a>
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 border-red-200"
                          onClick={() => setDeletingClipId(clip.id)}
                        >
                          <Trash2 className="w-4 h-4 mr-2" />
                          Delete
                        </Button>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Delete Task Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Generation</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this generation? This will permanently delete all clips and cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteTask} disabled={isDeleting} className="bg-red-600 hover:bg-red-700">
              {isDeleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Clip Confirmation Dialog */}
      <AlertDialog open={!!deletingClipId} onOpenChange={(open) => !open && setDeletingClipId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Clip</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this clip? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deletingClipId && handleDeleteClip(deletingClipId)}
              className="bg-red-600 hover:bg-red-700"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
