"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import { Button } from "@/components/ui/button";

interface TimelineDraftClip {
  id: string;
  clip_order: number;
  start_time: string;
  end_time: string;
  is_selected: boolean;
}

export type TimelineZoomLevel = number;

export interface DraftTimelineEditorHandle {
  /** Seek the video and scroll the timeline to center on the given time (seconds). */
  seekToTime: (seconds: number) => void;
}

interface DraftTimelineEditorProps {
  sourceVideoUrl: string | null;
  drafts: TimelineDraftClip[];
  conflictingClipIds?: string[];
  disabled?: boolean;
  minDurationSeconds?: number;
  maxDurationSeconds?: number;
  selectedClipId?: string | null;
  timelineZoomLevel?: TimelineZoomLevel;
  onDraftTimingChange: (draftId: string, startTime: string, endTime: string) => void;
  onAddDraft: (startTime: string, endTime: string) => void | Promise<string | null | void>;
  onSelectClip?: (clipId: string) => void;
  onTimelineZoomLevelChange?: (zoomLevel: TimelineZoomLevel) => void;
}

type DragMode = "move" | "resize-start" | "resize-end";
type NudgeBoundary = "start" | "end";

interface DragState {
  clipId: string;
  mode: DragMode;
  pointerStartX: number;
  startSeconds: number;
  endSeconds: number;
  minStart: number;
  maxEnd: number;
}

const TIMELINE_INCREMENT_SECONDS = 0.5;
const SNAP_THRESHOLD_SECONDS = 0.5;
const DEFAULT_NEW_CLIP_SECONDS = 8;
const TIMELINE_ZOOM_PRESETS: TimelineZoomLevel[] = [1, 2, 4];
const TIMELINE_MIN_ZOOM = 1;
const TIMELINE_MAX_ZOOM = 16;
const TIMELINE_WHEEL_ZOOM_SENSITIVITY = 0.002;
const TIMELINE_WAVEFORM_MIN_REQUEST_BINS = 400;
const TIMELINE_WAVEFORM_MAX_REQUEST_BINS = 5000;
const TIMELINE_WAVEFORM_FETCH_DEBOUNCE_MS = 120;
const TIMELINE_WAVEFORM_OVERSCAN_MULTIPLIER = 1;

interface TimelineWaveformPayload {
  peaks?: unknown;
  bins?: unknown;
  duration_seconds?: unknown;
  range_start_seconds?: unknown;
  range_end_seconds?: unknown;
}

interface TimelineWaveformData {
  peaks: number[];
  bins: number;
  durationSeconds: number;
  rangeStartSeconds: number;
  rangeEndSeconds: number;
}

function parseTimestampToSeconds(rawTimestamp: string): number {
  const value = (rawTimestamp || "").trim();
  if (!value) return 0;

  const parts = value.split(":");
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
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function snapToIncrement(seconds: number): number {
  return Math.max(0, Math.round(seconds / TIMELINE_INCREMENT_SECONDS) * TIMELINE_INCREMENT_SECONDS);
}

function formatSecondsToTimestamp(rawSeconds: number): string {
  const seconds = snapToIncrement(rawSeconds);
  const totalWhole = Math.floor(seconds);
  const hasHalf = Math.abs(seconds - totalWhole - 0.5) < 1e-6;
  const hours = Math.floor(totalWhole / 3600);
  const minutes = Math.floor((totalWhole % 3600) / 60);
  const remainder = totalWhole % 60;
  const secondToken = hasHalf ? `${remainder.toString().padStart(2, "0")}.5` : remainder.toString().padStart(2, "0");
  if (hours > 0) {
    return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${secondToken}`;
  }
  return `${minutes.toString().padStart(2, "0")}:${secondToken}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function clampZoomLevel(value: number): TimelineZoomLevel {
  if (!Number.isFinite(value)) return 1;
  return clamp(value, TIMELINE_MIN_ZOOM, TIMELINE_MAX_ZOOM);
}

function formatClock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(value / 60);
  const remaining = value % 60;
  return `${minutes.toString().padStart(2, "0")}:${remaining.toString().padStart(2, "0")}`;
}

function buildWaveformUrlFromSourceVideoUrl(
  sourceVideoUrl: string,
  bins: number,
  startSeconds?: number,
  endSeconds?: number,
): string | null {
  try {
    const parsedUrl = new URL(sourceVideoUrl, window.location.origin);
    if (!parsedUrl.pathname.endsWith("/source-video")) return null;
    parsedUrl.pathname = parsedUrl.pathname.replace(/\/source-video$/, "/waveform");
    parsedUrl.searchParams.set("bins", String(Math.max(300, Math.floor(bins))));
    if (typeof startSeconds === "number" && Number.isFinite(startSeconds)) {
      parsedUrl.searchParams.set("start_seconds", startSeconds.toFixed(3));
    } else {
      parsedUrl.searchParams.delete("start_seconds");
    }
    if (typeof endSeconds === "number" && Number.isFinite(endSeconds)) {
      parsedUrl.searchParams.set("end_seconds", endSeconds.toFixed(3));
    } else {
      parsedUrl.searchParams.delete("end_seconds");
    }
    return parsedUrl.toString();
  } catch {
    return null;
  }
}

export default forwardRef<DraftTimelineEditorHandle, DraftTimelineEditorProps>(function DraftTimelineEditor({
  sourceVideoUrl,
  drafts,
  conflictingClipIds = [],
  disabled = false,
  minDurationSeconds = 3,
  maxDurationSeconds = 180,
  selectedClipId,
  timelineZoomLevel,
  onDraftTimingChange,
  onAddDraft,
  onSelectClip,
  onTimelineZoomLevelChange,
}, ref) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const waveformCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const timelineScrollerRef = useRef<HTMLDivElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const pendingZoomAnchorRef = useRef<{ ratio: number; anchorX: number } | null>(null);
  const waveformRequestKeyRef = useRef<string>("");
  const [durationSeconds, setDurationSeconds] = useState(0);
  const [currentTimeSeconds, setCurrentTimeSeconds] = useState(0);
  const [internalSelectedClipId, setInternalSelectedClipId] = useState<string | null>(null);
  const [draggingClipId, setDraggingClipId] = useState<string | null>(null);
  const [internalZoomLevel, setInternalZoomLevel] = useState<TimelineZoomLevel>(1);
  const [showWaveform, setShowWaveform] = useState(true);
  const [waveformData, setWaveformData] = useState<TimelineWaveformData | null>(null);
  const [isWaveformLoading, setIsWaveformLoading] = useState(false);

  const preferredSelectedClipId = selectedClipId ?? internalSelectedClipId;
  const resolvedZoomLevel = timelineZoomLevel ?? internalZoomLevel;
  const hasWaveform = Boolean(waveformData && waveformData.peaks.length > 0);
  const conflictingClipIdSet = useMemo(() => new Set(conflictingClipIds), [conflictingClipIds]);

  const selectClip = useCallback(
    (clipId: string) => {
      if (selectedClipId === undefined) {
        setInternalSelectedClipId(clipId);
      }
      onSelectClip?.(clipId);
    },
    [onSelectClip, selectedClipId],
  );

  const handleZoomChange = useCallback(
    (nextZoom: TimelineZoomLevel) => {
      const clampedZoom = clampZoomLevel(nextZoom);
      if (timelineZoomLevel === undefined) {
        setInternalZoomLevel(clampedZoom);
      }
      onTimelineZoomLevelChange?.(clampedZoom);
    },
    [onTimelineZoomLevelChange, timelineZoomLevel],
  );

  const handleZoomWithAnchor = useCallback(
    (nextZoom: TimelineZoomLevel, anchorClientX?: number) => {
      const clampedZoom = clampZoomLevel(nextZoom);
      if (Math.abs(clampedZoom - resolvedZoomLevel) < 1e-3) return;

      const scroller = timelineScrollerRef.current;
      const track = trackRef.current;
      if (scroller && track) {
        const scrollerBounds = scroller.getBoundingClientRect();
        const anchorX =
          typeof anchorClientX === "number" && Number.isFinite(anchorClientX)
            ? clamp(anchorClientX - scrollerBounds.left, 0, scrollerBounds.width)
            : scrollerBounds.width / 2;
        const trackWidth = track.getBoundingClientRect().width;
        if (trackWidth > 0) {
          const ratio = clamp((scroller.scrollLeft + anchorX) / trackWidth, 0, 1);
          pendingZoomAnchorRef.current = { ratio, anchorX };
        }
      }

      handleZoomChange(clampedZoom);
    },
    [handleZoomChange, resolvedZoomLevel],
  );

  const draftWindows = useMemo(() => {
    return drafts
      .map((draft) => ({
        ...draft,
        startSeconds: snapToIncrement(parseTimestampToSeconds(draft.start_time)),
        endSeconds: snapToIncrement(parseTimestampToSeconds(draft.end_time)),
      }))
      .filter((draft) => draft.endSeconds > draft.startSeconds)
      .sort((a, b) => a.startSeconds - b.startSeconds || a.endSeconds - b.endSeconds || a.clip_order - b.clip_order);
  }, [drafts]);

  const resolvedSelectedClipId = useMemo(() => {
    if (preferredSelectedClipId && draftWindows.some((clip) => clip.id === preferredSelectedClipId)) {
      return preferredSelectedClipId;
    }
    return draftWindows[0]?.id ?? null;
  }, [draftWindows, preferredSelectedClipId]);

  const selectedClipIndex = useMemo(() => {
    if (!resolvedSelectedClipId) return -1;
    return draftWindows.findIndex((clip) => clip.id === resolvedSelectedClipId);
  }, [draftWindows, resolvedSelectedClipId]);

  const selectedClip = selectedClipIndex >= 0 ? draftWindows[selectedClipIndex] : null;

  const getTrackWidth = useCallback(() => {
    return trackRef.current?.getBoundingClientRect().width || 0;
  }, []);

  const seekVideo = useCallback((seconds: number) => {
    if (!videoRef.current || !Number.isFinite(seconds)) return;
    videoRef.current.currentTime = clamp(seconds, 0, durationSeconds || seconds);
  }, [durationSeconds]);

  /** Scroll the timeline track so that the given time ratio (0–1) is centered in view. */
  const scrollToTimeRatio = useCallback((ratio: number) => {
    const scroller = timelineScrollerRef.current;
    const track = trackRef.current;
    if (!scroller || !track) return;
    const trackWidth = track.getBoundingClientRect().width;
    if (trackWidth <= 0) return;
    const maxScrollLeft = Math.max(0, trackWidth - scroller.clientWidth);
    scroller.scrollLeft = clamp(ratio * trackWidth - scroller.clientWidth / 2, 0, maxScrollLeft);
  }, []);

  useImperativeHandle(ref, () => ({
    seekToTime(seconds: number) {
      if (!Number.isFinite(seconds) || !durationSeconds) return;
      seekVideo(seconds);
      setCurrentTimeSeconds(seconds);
      scrollToTimeRatio(seconds / durationSeconds);
    },
  }), [seekVideo, scrollToTimeRatio, durationSeconds]);

  useEffect(() => {
    if (!onSelectClip || selectedClipId === undefined) return;
    if (!resolvedSelectedClipId || selectedClipId === resolvedSelectedClipId) return;
    onSelectClip(resolvedSelectedClipId);
  }, [onSelectClip, resolvedSelectedClipId, selectedClipId]);

  useEffect(() => {
    const pendingAnchor = pendingZoomAnchorRef.current;
    if (!pendingAnchor) return;
    const scroller = timelineScrollerRef.current;
    const track = trackRef.current;
    if (!scroller || !track) return;

    const rafId = window.requestAnimationFrame(() => {
      const trackWidth = track.getBoundingClientRect().width;
      const maxScrollLeft = Math.max(0, trackWidth - scroller.clientWidth);
      scroller.scrollLeft = clamp(
        pendingAnchor.ratio * trackWidth - pendingAnchor.anchorX,
        0,
        maxScrollLeft,
      );
      pendingZoomAnchorRef.current = null;
    });

    return () => {
      window.cancelAnimationFrame(rafId);
    };
  }, [resolvedZoomLevel]);

  useEffect(() => {
    if (!videoRef.current) return;
    const video = videoRef.current;

    const handleLoadedMetadata = () => {
      setDurationSeconds(Number.isFinite(video.duration) ? Math.max(0, video.duration) : 0);
    };
    const handleTimeUpdate = () => {
      setCurrentTimeSeconds(video.currentTime || 0);
    };

    video.addEventListener("loadedmetadata", handleLoadedMetadata);
    video.addEventListener("timeupdate", handleTimeUpdate);
    return () => {
      video.removeEventListener("loadedmetadata", handleLoadedMetadata);
      video.removeEventListener("timeupdate", handleTimeUpdate);
    };
  }, [sourceVideoUrl]);

  const handleTimelineClick = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!durationSeconds) return;
      const bounds = event.currentTarget.getBoundingClientRect();
      if (!bounds.width) return;
      const ratio = clamp((event.clientX - bounds.left) / bounds.width, 0, 1);
      const targetTime = ratio * durationSeconds;
      setCurrentTimeSeconds(targetTime);
      seekVideo(targetTime);
    },
    [durationSeconds, seekVideo],
  );

  const handlePointerMove = useCallback(
    (event: PointerEvent) => {
      const dragState = dragStateRef.current;
      if (!dragState || disabled || durationSeconds <= 0) return;

      const width = getTrackWidth();
      if (!width) return;

      const deltaSeconds = ((event.clientX - dragState.pointerStartX) / width) * durationSeconds;
      const clipLength = dragState.endSeconds - dragState.startSeconds;

      let nextStart = dragState.startSeconds;
      let nextEnd = dragState.endSeconds;

      if (dragState.mode === "move") {
        nextStart = clamp(dragState.startSeconds + deltaSeconds, dragState.minStart, dragState.maxEnd - clipLength);
        nextEnd = nextStart + clipLength;
      } else if (dragState.mode === "resize-start") {
        nextStart = clamp(
          dragState.startSeconds + deltaSeconds,
          dragState.minStart,
          dragState.endSeconds - minDurationSeconds,
        );
        nextEnd = dragState.endSeconds;
      } else {
        nextStart = dragState.startSeconds;
        nextEnd = clamp(
          dragState.endSeconds + deltaSeconds,
          dragState.startSeconds + minDurationSeconds,
          dragState.maxEnd,
        );
      }

      nextStart = snapToIncrement(nextStart);
      nextEnd = snapToIncrement(nextEnd);

      if (dragState.mode === "move") {
        const minStart = dragState.minStart;
        const maxStart = dragState.maxEnd - clipLength;
        nextStart = clamp(nextStart, minStart, maxStart);
        nextEnd = nextStart + clipLength;
        if (Math.abs(nextStart - dragState.minStart) <= SNAP_THRESHOLD_SECONDS) {
          nextStart = dragState.minStart;
          nextEnd = nextStart + clipLength;
        }
        if (Math.abs(nextEnd - dragState.maxEnd) <= SNAP_THRESHOLD_SECONDS) {
          nextEnd = dragState.maxEnd;
          nextStart = nextEnd - clipLength;
        }
      } else if (dragState.mode === "resize-start") {
        if (Math.abs(nextStart - dragState.minStart) <= SNAP_THRESHOLD_SECONDS) {
          nextStart = dragState.minStart;
        }
        nextStart = clamp(nextStart, dragState.minStart, dragState.endSeconds - minDurationSeconds);
      } else {
        if (Math.abs(nextEnd - dragState.maxEnd) <= SNAP_THRESHOLD_SECONDS) {
          nextEnd = dragState.maxEnd;
        }
        nextEnd = clamp(nextEnd, dragState.startSeconds + minDurationSeconds, dragState.maxEnd);
      }

      if (nextEnd - nextStart > maxDurationSeconds) {
        if (dragState.mode === "resize-start") {
          nextStart = nextEnd - maxDurationSeconds;
        } else if (dragState.mode === "resize-end") {
          nextEnd = nextStart + maxDurationSeconds;
        }
      }

      onDraftTimingChange(
        dragState.clipId,
        formatSecondsToTimestamp(nextStart),
        formatSecondsToTimestamp(nextEnd),
      );
    },
    [disabled, durationSeconds, getTrackWidth, maxDurationSeconds, minDurationSeconds, onDraftTimingChange],
  );

  const handlePointerUp = useCallback(() => {
    dragStateRef.current = null;
    setDraggingClipId(null);
    window.removeEventListener("pointermove", handlePointerMove);
  }, [handlePointerMove]);

  const startDrag = useCallback(
    (
      event: ReactPointerEvent<HTMLDivElement>,
      clipId: string,
      mode: DragMode,
    ) => {
      if (disabled || durationSeconds <= 0) return;
      event.preventDefault();
      event.stopPropagation();

      const currentIndex = draftWindows.findIndex((clip) => clip.id === clipId);
      if (currentIndex === -1) return;
      const current = draftWindows[currentIndex];
      const previous = currentIndex > 0 ? draftWindows[currentIndex - 1] : null;
      const next = currentIndex < draftWindows.length - 1 ? draftWindows[currentIndex + 1] : null;

      dragStateRef.current = {
        clipId,
        mode,
        pointerStartX: event.clientX,
        startSeconds: current.startSeconds,
        endSeconds: current.endSeconds,
        minStart: previous ? previous.endSeconds : 0,
        maxEnd: next ? next.startSeconds : durationSeconds,
      };
      selectClip(clipId);
      setDraggingClipId(clipId);
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", handlePointerUp, { once: true });
    },
    [disabled, draftWindows, durationSeconds, handlePointerMove, handlePointerUp, selectClip],
  );

  useEffect(() => {
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", handlePointerUp);
    };
  }, [handlePointerMove, handlePointerUp]);

  const addClipDisabled = useMemo(() => {
    return disabled || !sourceVideoUrl || durationSeconds <= 0;
  }, [disabled, durationSeconds, sourceVideoUrl]);

  const handleAddAtPlayhead = useCallback(async () => {
    if (addClipDisabled) return;

    const windows = draftWindows;
    const gaps: Array<{ start: number; end: number }> = [];
    let cursor = 0;
    for (const clip of windows) {
      if (clip.startSeconds > cursor + 1e-6) {
        gaps.push({ start: cursor, end: clip.startSeconds });
      }
      cursor = Math.max(cursor, clip.endSeconds);
    }
    if (durationSeconds > cursor + 1e-6) {
      gaps.push({ start: cursor, end: durationSeconds });
    }
    if (windows.length === 0) {
      gaps.push({ start: 0, end: durationSeconds });
    }

    const validGaps = gaps.filter((gap) => gap.end - gap.start >= minDurationSeconds);
    if (!validGaps.length) return;

    const playhead = clamp(currentTimeSeconds, 0, durationSeconds);
    let chosenGap = validGaps.find((gap) => playhead >= gap.start && playhead <= gap.end) || null;
    if (!chosenGap) {
      chosenGap = validGaps.reduce((best, candidate) => {
        const bestDistance = Math.min(Math.abs(playhead - best.start), Math.abs(playhead - best.end));
        const candidateDistance = Math.min(Math.abs(playhead - candidate.start), Math.abs(playhead - candidate.end));
        return candidateDistance < bestDistance ? candidate : best;
      }, validGaps[0]);
    }

    const gapDuration = chosenGap.end - chosenGap.start;
    const clipDuration = Math.min(DEFAULT_NEW_CLIP_SECONDS, maxDurationSeconds, gapDuration);
    const rawStart = clamp(playhead, chosenGap.start, chosenGap.end - clipDuration);
    const startSeconds = snapToIncrement(rawStart);
    const endSeconds = snapToIncrement(startSeconds + clipDuration);
    if (endSeconds - startSeconds < minDurationSeconds) return;
    const createdClipId = await onAddDraft(
      formatSecondsToTimestamp(startSeconds),
      formatSecondsToTimestamp(endSeconds),
    );
    if (typeof createdClipId === "string" && createdClipId.trim()) {
      selectClip(createdClipId);
    }
  }, [
    addClipDisabled,
    currentTimeSeconds,
    draftWindows,
    durationSeconds,
    maxDurationSeconds,
    minDurationSeconds,
    onAddDraft,
    selectClip,
  ]);

  const handleNudgeBoundary = useCallback(
    (boundary: NudgeBoundary, deltaSeconds: number) => {
      if (disabled || selectedClipIndex < 0) return;
      const current = draftWindows[selectedClipIndex];
      if (!current) return;

      const previous = selectedClipIndex > 0 ? draftWindows[selectedClipIndex - 1] : null;
      const next = selectedClipIndex < draftWindows.length - 1 ? draftWindows[selectedClipIndex + 1] : null;

      let nextStart = current.startSeconds;
      let nextEnd = current.endSeconds;

      if (boundary === "start") {
        const minStart = previous ? previous.endSeconds : 0;
        const maxStart = current.endSeconds - minDurationSeconds;
        nextStart = clamp(snapToIncrement(current.startSeconds + deltaSeconds), minStart, maxStart);
        if (nextEnd - nextStart > maxDurationSeconds) {
          nextStart = nextEnd - maxDurationSeconds;
        }
        nextStart = clamp(snapToIncrement(nextStart), minStart, maxStart);
      } else {
        const maxTimelineEnd = durationSeconds > 0 ? durationSeconds : current.endSeconds;
        const minEnd = current.startSeconds + minDurationSeconds;
        const maxEnd = next ? next.startSeconds : maxTimelineEnd;
        nextEnd = clamp(snapToIncrement(current.endSeconds + deltaSeconds), minEnd, maxEnd);
        if (nextEnd - nextStart > maxDurationSeconds) {
          nextEnd = nextStart + maxDurationSeconds;
        }
        nextEnd = clamp(snapToIncrement(nextEnd), minEnd, maxEnd);
      }

      if (nextEnd - nextStart < minDurationSeconds) return;

      onDraftTimingChange(
        current.id,
        formatSecondsToTimestamp(nextStart),
        formatSecondsToTimestamp(nextEnd),
      );

      if (boundary === "start") {
        seekVideo(nextStart);
        setCurrentTimeSeconds(nextStart);
      }
    },
    [
      disabled,
      draftWindows,
      durationSeconds,
      maxDurationSeconds,
      minDurationSeconds,
      onDraftTimingChange,
      seekVideo,
      selectedClipIndex,
    ],
  );

  const handleClipKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>, clipId: string, startSeconds: number) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      selectClip(clipId);
      seekVideo(startSeconds);
      setCurrentTimeSeconds(startSeconds);
    },
    [seekVideo, selectClip],
  );

  const handleTimelineWheel = useCallback(
    (event: ReactWheelEvent<HTMLDivElement>) => {
      const scroller = timelineScrollerRef.current;
      if (!scroller) return;

      if (event.shiftKey) {
        event.preventDefault();
        const zoomDelta = event.deltaY !== 0 ? event.deltaY : event.deltaX;
        if (Math.abs(zoomDelta) < 1e-3) return;
        const nextZoom = clampZoomLevel(
          resolvedZoomLevel * Math.exp(-zoomDelta * TIMELINE_WHEEL_ZOOM_SENSITIVITY),
        );
        handleZoomWithAnchor(nextZoom, event.clientX);
        return;
      }

      event.preventDefault();
      const panDelta =
        Math.abs(event.deltaX) > Math.abs(event.deltaY) ? event.deltaX : event.deltaY;
      if (Math.abs(panDelta) < 1e-3) return;
      scroller.scrollLeft += panDelta;
    },
    [handleZoomWithAnchor, resolvedZoomLevel],
  );

  useEffect(() => {
    if (!sourceVideoUrl) {
      waveformRequestKeyRef.current = "";
      setWaveformData(null);
      setIsWaveformLoading(false);
    }
  }, [sourceVideoUrl]);

  useEffect(() => {
    if (!sourceVideoUrl || !showWaveform) {
      setIsWaveformLoading(false);
      return;
    }

    const scroller = timelineScrollerRef.current;
    const track = trackRef.current;
    if (!scroller || !track) {
      return;
    }

    let active = true;
    let debounceTimerId: number | null = null;
    let abortController: AbortController | null = null;
    let requestToken = 0;

    const fetchWaveformForViewport = async () => {
      const viewportWidth = Math.max(1, scroller.clientWidth || track.clientWidth || 1);
      const trackWidth = Math.max(1, track.clientWidth || viewportWidth);
      const dpr = window.devicePixelRatio || 1;
      const requestedBins = clamp(
        Math.round(viewportWidth * dpr * 1.6),
        TIMELINE_WAVEFORM_MIN_REQUEST_BINS,
        TIMELINE_WAVEFORM_MAX_REQUEST_BINS,
      );

      let startSeconds: number | undefined;
      let endSeconds: number | undefined;
      if (durationSeconds > 0) {
        const visibleStartRatio = clamp(scroller.scrollLeft / trackWidth, 0, 1);
        const visibleEndRatio = clamp((scroller.scrollLeft + viewportWidth) / trackWidth, 0, 1);
        const visibleStartSeconds = visibleStartRatio * durationSeconds;
        const visibleEndSeconds = visibleEndRatio * durationSeconds;
        const visibleDuration = Math.max(0.1, visibleEndSeconds - visibleStartSeconds);
        const overscan = visibleDuration * TIMELINE_WAVEFORM_OVERSCAN_MULTIPLIER;
        startSeconds = Math.max(0, visibleStartSeconds - overscan);
        endSeconds = Math.min(durationSeconds, visibleEndSeconds + overscan);
      }

      const waveformUrl = buildWaveformUrlFromSourceVideoUrl(
        sourceVideoUrl,
        requestedBins,
        startSeconds,
        endSeconds,
      );
      if (!waveformUrl) {
        setIsWaveformLoading(false);
        return;
      }

      const requestKey = [
        sourceVideoUrl,
        requestedBins,
        typeof startSeconds === "number" ? startSeconds.toFixed(2) : "full",
        typeof endSeconds === "number" ? endSeconds.toFixed(2) : "full",
      ].join("|");
      if (requestKey === waveformRequestKeyRef.current) {
        return;
      }
      waveformRequestKeyRef.current = requestKey;

      if (abortController) {
        abortController.abort();
      }
      abortController = new AbortController();
      const activeRequestToken = ++requestToken;
      setIsWaveformLoading(true);

      try {
        const response = await fetch(waveformUrl, {
          signal: abortController.signal,
          cache: "no-store",
        });
        if (!response.ok) {
          throw new Error(`Waveform request failed (${response.status})`);
        }

        const payload = (await response.json()) as TimelineWaveformPayload;
        const normalizedPeaks = Array.isArray(payload.peaks)
          ? payload.peaks
              .map((value) => (typeof value === "number" ? value : Number(value)))
              .filter((value) => Number.isFinite(value))
              .map((value) => clamp(value, 0, 1))
          : [];

        const payloadDuration =
          typeof payload.duration_seconds === "number" ? payload.duration_seconds : Number(payload.duration_seconds);
        const resolvedDuration =
          Number.isFinite(payloadDuration) && payloadDuration > 0
            ? payloadDuration
            : durationSeconds > 0
              ? durationSeconds
              : 0;

        const payloadRangeStart =
          typeof payload.range_start_seconds === "number"
            ? payload.range_start_seconds
            : Number(payload.range_start_seconds);
        const payloadRangeEnd =
          typeof payload.range_end_seconds === "number"
            ? payload.range_end_seconds
            : Number(payload.range_end_seconds);
        const fallbackRangeStart = typeof startSeconds === "number" ? startSeconds : 0;
        const fallbackRangeEnd =
          typeof endSeconds === "number"
            ? endSeconds
            : resolvedDuration > 0
              ? resolvedDuration
              : fallbackRangeStart + 1;

        const rangeStart = clamp(
          Number.isFinite(payloadRangeStart) ? payloadRangeStart : fallbackRangeStart,
          0,
          resolvedDuration > 0 ? resolvedDuration : fallbackRangeEnd,
        );
        const minRangeEnd = resolvedDuration > 0 ? Math.min(resolvedDuration, rangeStart + 0.001) : rangeStart + 0.001;
        const rangeEndCandidate = Number.isFinite(payloadRangeEnd) ? payloadRangeEnd : fallbackRangeEnd;
        const rangeEnd =
          resolvedDuration > 0
            ? clamp(rangeEndCandidate, minRangeEnd, resolvedDuration)
            : Math.max(minRangeEnd, rangeEndCandidate);
        const payloadBins = typeof payload.bins === "number" ? payload.bins : Number(payload.bins);

        if (!active || activeRequestToken !== requestToken) {
          return;
        }

        if (normalizedPeaks.length === 0) {
          setWaveformData(null);
        } else {
          setWaveformData({
            peaks: normalizedPeaks,
            bins: Number.isFinite(payloadBins) ? Math.max(1, Math.floor(payloadBins)) : normalizedPeaks.length,
            durationSeconds: resolvedDuration > 0 ? resolvedDuration : rangeEnd,
            rangeStartSeconds: rangeStart,
            rangeEndSeconds: rangeEnd,
          });
        }
      } catch (waveformError) {
        if ((waveformError as { name?: string })?.name === "AbortError") {
          return;
        }
        waveformRequestKeyRef.current = "";
        console.warn("Failed to load timeline waveform:", waveformError);
      } finally {
        if (active && activeRequestToken === requestToken) {
          setIsWaveformLoading(false);
        }
      }
    };

    const scheduleWaveformFetch = (immediate = false) => {
      if (debounceTimerId !== null) {
        window.clearTimeout(debounceTimerId);
      }
      debounceTimerId = window.setTimeout(
        () => {
          void fetchWaveformForViewport();
        },
        immediate ? 0 : TIMELINE_WAVEFORM_FETCH_DEBOUNCE_MS,
      );
    };

    const handleScroll = () => {
      scheduleWaveformFetch(false);
    };

    const resizeObserver = typeof ResizeObserver !== "undefined"
      ? new ResizeObserver(() => {
          scheduleWaveformFetch(false);
        })
      : null;

    scroller.addEventListener("scroll", handleScroll, { passive: true });
    resizeObserver?.observe(scroller);
    resizeObserver?.observe(track);

    scheduleWaveformFetch(true);

    return () => {
      active = false;
      if (debounceTimerId !== null) {
        window.clearTimeout(debounceTimerId);
      }
      scroller.removeEventListener("scroll", handleScroll);
      resizeObserver?.disconnect();
      if (abortController) {
        abortController.abort();
      }
    };
  }, [durationSeconds, resolvedZoomLevel, showWaveform, sourceVideoUrl]);

  const drawWaveform = useCallback(() => {
    const canvas = waveformCanvasRef.current;
    const track = trackRef.current;
    if (!canvas || !track) return;

    const cssWidth = Math.max(1, Math.floor(track.clientWidth));
    const cssHeight = Math.max(1, Math.floor(track.clientHeight));
    const dpr = window.devicePixelRatio || 1;
    const pixelWidth = Math.max(1, Math.floor(cssWidth * dpr));
    const pixelHeight = Math.max(1, Math.floor(cssHeight * dpr));
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;

    const context = canvas.getContext("2d");
    if (!context) return;

    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    if (!showWaveform || !hasWaveform || !waveformData) return;

    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.strokeStyle = "rgba(148,163,184,0.52)";
    context.lineWidth = 1;
    context.beginPath();

    const timelineDuration = durationSeconds > 0 ? durationSeconds : waveformData.durationSeconds;
    if (!Number.isFinite(timelineDuration) || timelineDuration <= 0) return;

    const midline = cssHeight / 2;
    const amplitudeRange = Math.max(3, cssHeight / 2 - 7);
    const peakCount = waveformData.peaks.length;
    const denominator = Math.max(1, peakCount - 1);
    const rangeStartSeconds = clamp(waveformData.rangeStartSeconds, 0, timelineDuration);
    const rangeEndSeconds = clamp(waveformData.rangeEndSeconds, rangeStartSeconds + 0.001, timelineDuration);
    const rangeSpanSeconds = Math.max(0.001, rangeEndSeconds - rangeStartSeconds);
    const rangeStartX = (rangeStartSeconds / timelineDuration) * cssWidth;
    const rangeSpanX = (rangeSpanSeconds / timelineDuration) * cssWidth;

    for (let index = 0; index < peakCount; index += 1) {
      const peak = waveformData.peaks[index];
      const x = rangeStartX + (index / denominator) * rangeSpanX;
      const amplitude = amplitudeRange * peak;
      context.moveTo(x, midline - amplitude);
      context.lineTo(x, midline + amplitude);
    }
    context.stroke();
  }, [durationSeconds, hasWaveform, showWaveform, waveformData]);

  useEffect(() => {
    drawWaveform();
  }, [drawWaveform, resolvedZoomLevel]);

  useEffect(() => {
    const track = trackRef.current;
    if (!track || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      drawWaveform();
    });
    observer.observe(track);
    return () => observer.disconnect();
  }, [drawWaveform]);

  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-[0_8px_22px_-18px_rgba(15,23,42,0.55)] dark:border-slate-700 dark:bg-slate-900/75 dark:shadow-[0_10px_28px_-22px_rgba(2,6,23,0.95)]">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Source Timeline{" "}
            {durationSeconds > 0 ? `(${formatClock(currentTimeSeconds)} / ${formatClock(durationSeconds)})` : ""}
          </p>
          <p className="text-[11px] text-slate-500 dark:text-slate-400">
            Drag clips to move, use side handles to resize, or nudge boundaries by 0.5s.
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          onClick={() => void handleAddAtPlayhead()}
          disabled={addClipDisabled}
        >
          Add Clip At Playhead
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2.5 dark:border-slate-700 dark:bg-slate-800/70">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Zoom</span>
          {TIMELINE_ZOOM_PRESETS.map((zoom) => (
            <Button
              key={zoom}
              type="button"
              size="sm"
              variant={Math.abs(resolvedZoomLevel - zoom) < 1e-3 ? "default" : "outline"}
              className={`h-7 px-2 text-xs ${
                Math.abs(resolvedZoomLevel - zoom) < 1e-3
                  ? "shadow-sm"
                  : "border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
              }`}
              onClick={() => handleZoomWithAnchor(zoom)}
            >
              {zoom}x
            </Button>
          ))}
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            {`${(Math.round(resolvedZoomLevel * 10) / 10).toFixed(1)}x`}
          </span>
          <Button
            type="button"
            size="sm"
            variant={showWaveform ? "default" : "outline"}
            className={`h-7 px-2 text-xs ${
              showWaveform
                ? "shadow-sm"
                : "border-slate-300 bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
            }`}
            onClick={() => setShowWaveform((previous) => !previous)}
            disabled={!sourceVideoUrl}
          >
            Waveform {showWaveform ? "On" : "Off"}
          </Button>
          {showWaveform && sourceVideoUrl && (
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              {isWaveformLoading ? "Loading..." : hasWaveform ? "Loaded" : "Unavailable"}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-700 dark:text-slate-300">Nudge</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 border-slate-300 bg-slate-50 px-2 text-xs dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
            onClick={() => handleNudgeBoundary("start", -TIMELINE_INCREMENT_SECONDS)}
            disabled={disabled || !selectedClip}
          >
            Start -0.5s
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 border-slate-300 bg-slate-50 px-2 text-xs dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
            onClick={() => handleNudgeBoundary("start", TIMELINE_INCREMENT_SECONDS)}
            disabled={disabled || !selectedClip}
          >
            Start +0.5s
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 border-slate-300 bg-slate-50 px-2 text-xs dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
            onClick={() => handleNudgeBoundary("end", -TIMELINE_INCREMENT_SECONDS)}
            disabled={disabled || !selectedClip}
          >
            End -0.5s
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 border-slate-300 bg-slate-50 px-2 text-xs dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
            onClick={() => handleNudgeBoundary("end", TIMELINE_INCREMENT_SECONDS)}
            disabled={disabled || !selectedClip}
          >
            End +0.5s
          </Button>
        </div>
      </div>

      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        Shift + wheel to zoom, wheel to pan horizontally.
      </p>

      {sourceVideoUrl ? (
        <video
          ref={videoRef}
          src={sourceVideoUrl}
          controls
          preload="metadata"
          className="w-full max-h-[360px] rounded-lg border border-slate-200 bg-black dark:border-slate-700"
        />
      ) : (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-xs text-slate-500 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-300">
          Source video is not ready for timeline editing.
        </div>
      )}

      <div
        ref={timelineScrollerRef}
        className="overflow-x-auto pb-1"
        onWheel={handleTimelineWheel}
      >
        <div
          ref={trackRef}
          className="relative h-24 min-w-full rounded-lg border border-slate-200 bg-[linear-gradient(to_right,rgba(148,163,184,0.12)_1px,transparent_1px)] bg-[size:28px_100%] bg-slate-50 dark:border-slate-700 dark:bg-[linear-gradient(to_right,rgba(148,163,184,0.2)_1px,transparent_1px)] dark:bg-[size:28px_100%] dark:bg-slate-900"
          style={{ width: `${resolvedZoomLevel * 100}%` }}
          onClick={handleTimelineClick}
        >
          {showWaveform && (
            <canvas
              ref={waveformCanvasRef}
              className="pointer-events-none absolute inset-0 z-0"
              aria-hidden
            />
          )}
          {durationSeconds > 0 && (
            <div
              className="pointer-events-none absolute top-0 z-10 h-full w-[2px] bg-red-500/90 shadow-[0_0_0_2px_rgba(239,68,68,0.12)]"
              style={{ left: `${(clamp(currentTimeSeconds, 0, durationSeconds) / durationSeconds) * 100}%` }}
            />
          )}
          {durationSeconds > 0 &&
            draftWindows.map((clip, displayIndex) => {
              const left = (clip.startSeconds / durationSeconds) * 100;
              const width = ((clip.endSeconds - clip.startSeconds) / durationSeconds) * 100;
              const isActive = resolvedSelectedClipId === clip.id;
              const isConflicting = conflictingClipIdSet.has(clip.id);
              return (
                <div
                  key={clip.id}
                  role="button"
                  tabIndex={disabled ? -1 : 0}
                  aria-pressed={isActive}
                  aria-label={`Clip ${displayIndex + 1}: ${formatClock(clip.startSeconds)} to ${formatClock(clip.endSeconds)}`}
                  className={`absolute top-9 h-6 rounded-md border text-[10px] text-white outline-none transition ${
                    isConflicting
                      ? "border-red-700 bg-red-600/60"
                      : clip.is_selected
                        ? "border-blue-700 bg-blue-600/55"
                        : "border-slate-500 bg-slate-500/50"
                  } ${isActive ? "ring-2 ring-amber-400 ring-offset-1 ring-offset-slate-900" : ""} ${draggingClipId === clip.id ? "cursor-grabbing" : "cursor-grab"}`}
                  style={{ left: `${left}%`, width: `${Math.max(width, 1.4)}%` }}
                  onPointerDown={(event) => startDrag(event, clip.id, "move")}
                  onKeyDown={(event) => handleClipKeyDown(event, clip.id, clip.startSeconds)}
                >
                  <div
                    className="absolute left-0 top-0 h-full w-3 min-w-[12px] cursor-ew-resize rounded-l bg-white/45 dark:bg-slate-100/35"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      startDrag(event, clip.id, "resize-start");
                    }}
                  />
                  <div
                    className="absolute right-0 top-0 h-full w-3 min-w-[12px] cursor-ew-resize rounded-r bg-white/45 dark:bg-slate-100/35"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      startDrag(event, clip.id, "resize-end");
                    }}
                  />
                  <button
                    type="button"
                    className="h-full w-full truncate px-3 text-left"
                    onClick={(event) => {
                      event.stopPropagation();
                      selectClip(clip.id);
                      seekVideo(clip.startSeconds);
                      setCurrentTimeSeconds(clip.startSeconds);
                    }}
                  >
                    Clip {displayIndex + 1}
                  </button>
                </div>
              );
            })}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 dark:text-slate-400">
        {selectedClip
          ? `Active clip: ${formatSecondsToTimestamp(selectedClip.startSeconds)} -> ${formatSecondsToTimestamp(selectedClip.endSeconds)}`
          : "Select a clip to fine-tune timing."}
      </p>
    </div>
  );
});
