"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, CheckCircle, Clock, Loader2, Timer, Youtube } from "lucide-react";
import { useSession } from "@/lib/auth-client";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { AI_FOCUS_TAG_OPTIONS, formatAiFocusTag, type AiFocusTag } from "@/lib/ai-focus-tags";
import { OUTPUT_ASPECT_RATIO_OPTIONS, formatOutputAspectRatioSummary } from "@/lib/output-aspect-ratios";
import {
  getWorkflowSelectionDescription,
  getWorkflowSelectionLabel,
  getWorkflowSelectionMetadata,
  getWorkflowSelectionValue,
  getWorkflowSelectValue,
  parseWorkflowSelectValue,
  PROCESSING_PROFILE_PRESETS,
  resolveWorkflowSelection,
  type SavedWorkflow,
  type WorkflowSelection,
} from "@/lib/processing-profiles";
import { formatSourceTypeLabel, getTaskRuntimeSummary, isHttpUrl } from "@/lib/task-metadata";
import {
  DEFAULT_AI_MODELS,
  DEFAULT_USER_PREFERENCES,
  isAiProvider,
  isDefaultFramingMode,
  isFaceAnchorProfile,
  isFaceDetectionMode,
  isFallbackCropPosition,
  isOutputAspectRatio,
  isPersistedProcessingProfile,
  isWorkflowSource,
  isTranscriptionProvider,
  isWhisperDevicePreference,
  isWhisperModelSize,
  normalizeReviewAutoSelectStrongFaceMinScorePercent,
  type AiProvider,
  type UserPreferences,
} from "./settings/settings-section-types";
import { normalizeFontStyleOptions } from "@/lib/font-style-options";

interface LatestTask {
  id: string;
  source_title: string;
  source_type: string;
  source_url?: string | null;
  status: string;
  progress_message?: string;
  clips_count: number;
  created_at: string;
  updated_at: string;
  runtime_info?: Record<string, unknown>;
}

const MAX_AI_FOCUS_TAGS = 4;

function formatProviderLabel(provider: AiProvider): string {
  if (provider === "zai") {
    return "z.ai";
  }
  if (provider === "ollama") {
    return "Ollama";
  }
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

export default function Home() {
  const router = useRouter();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const { data: session, isPending } = useSession();

  const [url, setUrl] = useState("");
  const [sourceType, setSourceType] = useState<"youtube" | "upload">("youtube");
  const [fileName, setFileName] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [aiFocusTags, setAiFocusTags] = useState<AiFocusTag[]>([]);
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_USER_PREFERENCES);
  const [savedWorkflows, setSavedWorkflows] = useState<SavedWorkflow[]>([]);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowSelection>({ kind: "built_in", id: "balanced" });
  const [selectedOutputAspectRatio, setSelectedOutputAspectRatio] = useState<UserPreferences["defaultOutputAspectRatio"]>(
    DEFAULT_USER_PREFERENCES.defaultOutputAspectRatio,
  );
  const [latestTask, setLatestTask] = useState<LatestTask | null>(null);
  const [isLoadingLatest, setIsLoadingLatest] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [hasLoadedPreferences, setHasLoadedPreferences] = useState(false);
  const [hasLoadedWorkflows, setHasLoadedWorkflows] = useState(false);

  const youtubeInputRef = useRef<HTMLInputElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const fileRef = useRef<File | null>(null);
  const selectedOptionCardClass = "border-black bg-black text-white";

  const defaultWorkflowValues = useMemo(
    () => ({
      reviewBeforeRenderEnabled: preferences.reviewBeforeRenderEnabled,
      timelineEditorEnabled: preferences.timelineEditorEnabled,
      transitionsEnabled: preferences.transitionsEnabled,
      transcriptionProvider: preferences.transcriptionProvider,
      whisperModelSize: preferences.whisperModelSize,
      defaultFramingMode: preferences.defaultFramingMode,
      faceDetectionMode: preferences.faceDetectionMode,
      fallbackCropPosition: preferences.fallbackCropPosition,
      faceAnchorProfile: preferences.faceAnchorProfile,
    }),
    [preferences],
  );

  const effectiveWorkflowValues = useMemo(
    () => getWorkflowSelectionValue(selectedWorkflow, savedWorkflows) ?? defaultWorkflowValues,
    [defaultWorkflowValues, savedWorkflows, selectedWorkflow],
  );

  const summaryItems = useMemo(
    () => [
      {
        label: "Captions",
        value: `${preferences.fontFamily} · ${preferences.fontSize}px`,
      },
      {
        label: "Framing",
        value: `${formatOutputAspectRatioSummary(selectedOutputAspectRatio)} · ${effectiveWorkflowValues.defaultFramingMode.replace(/_/g, " ")}`,
      },
      {
        label: "Transcription",
        value:
          effectiveWorkflowValues.transcriptionProvider === "assemblyai"
            ? "AssemblyAI"
            : `Local Whisper · ${effectiveWorkflowValues.whisperModelSize}`,
      },
      {
        label: "AI model",
        value: `${formatProviderLabel(preferences.aiProvider)} · ${preferences.aiModel.trim() || DEFAULT_AI_MODELS[preferences.aiProvider]}`,
      },
    ],
    [effectiveWorkflowValues, preferences, selectedOutputAspectRatio],
  );

  const toggleAiFocusTag = (tag: AiFocusTag) => {
    setAiFocusTags((current) => {
      if (current.includes(tag)) {
        return current.filter((value) => value !== tag);
      }
      if (current.length >= MAX_AI_FOCUS_TAGS) {
        return current;
      }
      return [...current, tag];
    });
  };

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }

    const loadPreferences = async () => {
      try {
        const response = await fetch("/api/preferences");
        if (!response.ok) {
          return;
        }
        const data: Partial<UserPreferences> = await response.json();
        const resolvedAiProvider =
          typeof data.aiProvider === "string" && isAiProvider(data.aiProvider) ? data.aiProvider : "openai";
        const normalizedFontStyle = normalizeFontStyleOptions(data);

        const nextPreferences: UserPreferences = {
          ...normalizedFontStyle,
          transitionsEnabled: Boolean(data.transitionsEnabled),
          reviewBeforeRenderEnabled:
            typeof data.reviewBeforeRenderEnabled === "boolean"
              ? data.reviewBeforeRenderEnabled
              : DEFAULT_USER_PREFERENCES.reviewBeforeRenderEnabled,
          timelineEditorEnabled:
            typeof data.timelineEditorEnabled === "boolean"
              ? data.timelineEditorEnabled
              : DEFAULT_USER_PREFERENCES.timelineEditorEnabled,
          defaultProcessingProfile:
            typeof data.defaultProcessingProfile === "string" && isPersistedProcessingProfile(data.defaultProcessingProfile)
              ? data.defaultProcessingProfile
              : DEFAULT_USER_PREFERENCES.defaultProcessingProfile,
          defaultWorkflowSource:
            typeof data.defaultWorkflowSource === "string" && isWorkflowSource(data.defaultWorkflowSource)
              ? data.defaultWorkflowSource
              : DEFAULT_USER_PREFERENCES.defaultWorkflowSource,
          defaultSavedWorkflowId:
            typeof data.defaultSavedWorkflowId === "string" && data.defaultSavedWorkflowId.trim().length > 0
              ? data.defaultSavedWorkflowId
              : null,
          reviewAutoSelectStrongFaceEnabled:
            typeof data.reviewAutoSelectStrongFaceEnabled === "boolean"
              ? data.reviewAutoSelectStrongFaceEnabled
              : DEFAULT_USER_PREFERENCES.reviewAutoSelectStrongFaceEnabled,
          reviewAutoSelectStrongFaceMinScorePercent: normalizeReviewAutoSelectStrongFaceMinScorePercent(
            data.reviewAutoSelectStrongFaceMinScorePercent,
          ),
          defaultFramingMode:
            typeof data.defaultFramingMode === "string" && isDefaultFramingMode(data.defaultFramingMode)
              ? data.defaultFramingMode
              : DEFAULT_USER_PREFERENCES.defaultFramingMode,
          faceDetectionMode:
            typeof data.faceDetectionMode === "string" && isFaceDetectionMode(data.faceDetectionMode)
              ? data.faceDetectionMode
              : DEFAULT_USER_PREFERENCES.faceDetectionMode,
          fallbackCropPosition:
            typeof data.fallbackCropPosition === "string" && isFallbackCropPosition(data.fallbackCropPosition)
              ? data.fallbackCropPosition
              : DEFAULT_USER_PREFERENCES.fallbackCropPosition,
          faceAnchorProfile:
            typeof data.faceAnchorProfile === "string" && isFaceAnchorProfile(data.faceAnchorProfile)
              ? data.faceAnchorProfile
              : DEFAULT_USER_PREFERENCES.faceAnchorProfile,
          defaultOutputAspectRatio:
            typeof data.defaultOutputAspectRatio === "string" && isOutputAspectRatio(data.defaultOutputAspectRatio)
              ? data.defaultOutputAspectRatio
              : DEFAULT_USER_PREFERENCES.defaultOutputAspectRatio,
          transcriptionProvider:
            typeof data.transcriptionProvider === "string" && isTranscriptionProvider(data.transcriptionProvider)
              ? data.transcriptionProvider
              : DEFAULT_USER_PREFERENCES.transcriptionProvider,
          whisperChunkingEnabled:
            typeof data.whisperChunkingEnabled === "boolean"
              ? data.whisperChunkingEnabled
              : DEFAULT_USER_PREFERENCES.whisperChunkingEnabled,
          whisperChunkDurationSeconds:
            typeof data.whisperChunkDurationSeconds === "number"
              ? data.whisperChunkDurationSeconds
              : DEFAULT_USER_PREFERENCES.whisperChunkDurationSeconds,
          whisperChunkOverlapSeconds:
            typeof data.whisperChunkOverlapSeconds === "number"
              ? data.whisperChunkOverlapSeconds
              : DEFAULT_USER_PREFERENCES.whisperChunkOverlapSeconds,
          taskTimeoutSeconds:
            typeof data.taskTimeoutSeconds === "number"
              ? data.taskTimeoutSeconds
              : DEFAULT_USER_PREFERENCES.taskTimeoutSeconds,
          whisperModelSize:
            typeof data.whisperModelSize === "string" && isWhisperModelSize(data.whisperModelSize)
              ? data.whisperModelSize
              : DEFAULT_USER_PREFERENCES.whisperModelSize,
          whisperDevice:
            typeof data.whisperDevice === "string" && isWhisperDevicePreference(data.whisperDevice)
              ? data.whisperDevice
              : DEFAULT_USER_PREFERENCES.whisperDevice,
          whisperGpuIndex:
            typeof data.whisperGpuIndex === "number" && Number.isInteger(data.whisperGpuIndex) && data.whisperGpuIndex >= 0
              ? data.whisperGpuIndex
              : DEFAULT_USER_PREFERENCES.whisperGpuIndex,
          aiProvider: resolvedAiProvider,
          aiModel:
            typeof data.aiModel === "string" && data.aiModel.trim().length > 0
              ? data.aiModel.trim()
              : DEFAULT_AI_MODELS[resolvedAiProvider],
        };

        setPreferences(nextPreferences);
        setSelectedOutputAspectRatio(nextPreferences.defaultOutputAspectRatio);
        setHasLoadedPreferences(true);
      } catch (loadError) {
        console.error("Failed to load preferences:", loadError);
      } finally {
        setHasLoadedPreferences(true);
      }
    };

    void loadPreferences();
  }, [session?.user?.id]);

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }

    const loadWorkflows = async () => {
      try {
        const response = await fetch("/api/workflows");
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as { workflows?: SavedWorkflow[] };
        setSavedWorkflows(Array.isArray(data.workflows) ? data.workflows : []);
      } catch (loadError) {
        console.error("Failed to load workflows:", loadError);
      } finally {
        setHasLoadedWorkflows(true);
      }
    };

    void loadWorkflows();
  }, [session?.user?.id]);

  useEffect(() => {
    if (!hasLoadedPreferences || !hasLoadedWorkflows) {
      return;
    }
    setSelectedWorkflow(
      resolveWorkflowSelection({
        values: defaultWorkflowValues,
        savedWorkflows,
        persistedSource: preferences.defaultWorkflowSource,
        persistedBuiltInProfile: preferences.defaultProcessingProfile,
        persistedSavedWorkflowId: preferences.defaultSavedWorkflowId,
      }),
    );
  }, [defaultWorkflowValues, hasLoadedPreferences, hasLoadedWorkflows, preferences.defaultProcessingProfile, preferences.defaultSavedWorkflowId, preferences.defaultWorkflowSource, savedWorkflows]);

  const fetchLatestTask = useCallback(
    async (showLoader = true) => {
      if (!session?.user?.id) return;
      try {
        if (showLoader) {
          setIsLoadingLatest(true);
        }
        const response = await fetch(`${apiUrl}/tasks/`, {
          headers: { user_id: session.user.id },
        });
        if (response.ok) {
          const data = await response.json();
          if (data.tasks && data.tasks.length > 0) {
            setLatestTask(data.tasks[0]);
          } else {
            setLatestTask(null);
          }
        }
      } catch (latestTaskError) {
        console.error("Failed to load latest task:", latestTaskError);
      } finally {
        if (showLoader) {
          setIsLoadingLatest(false);
        }
      }
    },
    [apiUrl, session?.user?.id],
  );

  useEffect(() => {
    void fetchLatestTask(true);
  }, [fetchLatestTask]);

  useEffect(() => {
    setNowMs(Date.now());
    if (!latestTask?.status || (latestTask.status !== "queued" && latestTask.status !== "processing" && latestTask.status !== "awaiting_review")) {
      return;
    }
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [latestTask?.status]);

  useEffect(() => {
    if (!latestTask?.status || (latestTask.status !== "queued" && latestTask.status !== "processing")) {
      return;
    }
    const intervalId = window.setInterval(() => {
      void fetchLatestTask(false);
    }, 4000);
    return () => window.clearInterval(intervalId);
  }, [fetchLatestTask, latestTask?.status]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] || null;
    fileRef.current = file;
    setFileName(file ? file.name : null);
  };

  const uploadVideoWithProgress = (file: File): Promise<{ video_path?: string; message?: string }> => {
    return new Promise((resolve, reject) => {
      const formData = new FormData();
      formData.append("video", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${apiUrl}/upload`);

      xhr.upload.onprogress = (event) => {
        if (!event.lengthComputable || event.total <= 0) {
          return;
        }
        const uploadPercent = Math.round((event.loaded / event.total) * 100);
        const progressValue = Math.max(5, Math.min(95, Math.round(uploadPercent * 0.95)));
        setProgress(progressValue);
        setStatusMessage(`Uploading video file... ${uploadPercent}%`);
      };

      xhr.onload = () => {
        const isSuccess = xhr.status >= 200 && xhr.status < 300;
        if (!isSuccess) {
          let detail = xhr.responseText || `HTTP ${xhr.status}`;
          try {
            const parsed = JSON.parse(xhr.responseText) as { detail?: string };
            if (parsed?.detail) {
              detail = parsed.detail;
            }
          } catch {
            // Keep raw response text when JSON parsing fails.
          }
          reject(new Error(`Upload error: ${detail}`));
          return;
        }

        try {
          const response = JSON.parse(xhr.responseText) as { video_path?: string; message?: string };
          resolve(response);
        } catch {
          reject(new Error("Upload error: invalid response from server"));
        }
      };

      xhr.onerror = () => {
        reject(new Error("Upload error: network failure"));
      };

      xhr.send(formData);
    });
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (sourceType === "upload" && !fileRef.current) return;
    if (sourceType === "youtube" && !url.trim()) return;
    if (!session?.user?.id) return;

    setIsLoading(true);
    setProgress(0);
    setError(null);
    setStatusMessage("");

    try {
      let videoUrl = url;

      if (sourceType === "upload" && fileRef.current) {
        setStatusMessage("Uploading video file...");
        setProgress(5);
        const uploadResult = await uploadVideoWithProgress(fileRef.current);
        if (!uploadResult.video_path) {
          throw new Error("Upload error: server did not return uploaded file path");
        }
        setStatusMessage("Upload complete. Starting processing...");
        setProgress(100);
        videoUrl = uploadResult.video_path;
      }

      const workflowPayload = effectiveWorkflowValues;
      const workflowMetadata = getWorkflowSelectionMetadata(selectedWorkflow, savedWorkflows);

      const startRequestPayload: Record<string, unknown> = {
        source: {
          url: videoUrl,
          title: null,
        },
        processing_profile: workflowMetadata.processingProfile,
        workflow_source: workflowMetadata.workflowSource,
        saved_workflow_id: workflowMetadata.savedWorkflowId,
        workflow_name_snapshot: workflowMetadata.workflowNameSnapshot,
        review_before_render_enabled: workflowPayload.reviewBeforeRenderEnabled,
        timeline_editor_enabled: workflowPayload.timelineEditorEnabled,
        video_options: {
          default_framing_mode: workflowPayload.defaultFramingMode,
          face_detection_mode: workflowPayload.faceDetectionMode,
          fallback_crop_position: workflowPayload.fallbackCropPosition,
          face_anchor_profile: workflowPayload.faceAnchorProfile,
          output_aspect_ratio: selectedOutputAspectRatio,
        },
        font_options: {
          font_family: preferences.fontFamily,
          font_size: preferences.fontSize,
          font_color: preferences.fontColor,
          highlight_color: preferences.highlightColor,
          font_weight: preferences.fontWeight,
          line_height: preferences.lineHeight,
          letter_spacing: preferences.letterSpacing,
          text_transform: preferences.textTransform,
          text_align: preferences.textAlign,
          stroke_color: preferences.strokeColor,
          stroke_width: preferences.strokeWidth,
          stroke_blur: preferences.strokeBlur,
          shadow_color: preferences.shadowColor,
          shadow_opacity: preferences.shadowOpacity,
          shadow_blur: preferences.shadowBlur,
          shadow_offset_x: preferences.shadowOffsetX,
          shadow_offset_y: preferences.shadowOffsetY,
          dim_unhighlighted: preferences.dimUnhighlighted,
          transitions_enabled: workflowPayload.transitionsEnabled,
        },
        transcription_options: {
          provider: workflowPayload.transcriptionProvider,
          whisper_chunking_enabled: preferences.whisperChunkingEnabled,
          whisper_chunk_duration_seconds: preferences.whisperChunkDurationSeconds,
          whisper_chunk_overlap_seconds: preferences.whisperChunkOverlapSeconds,
          task_timeout_seconds: preferences.taskTimeoutSeconds,
          whisper_model_size: workflowPayload.whisperModelSize,
          whisper_device: preferences.whisperDevice,
          whisper_gpu_index: preferences.whisperGpuIndex,
        },
        ai_options: {
          provider: preferences.aiProvider,
          model: preferences.aiModel.trim() || DEFAULT_AI_MODELS[preferences.aiProvider],
          focus_tags: aiFocusTags,
        },
      };

      if (workflowPayload.reviewBeforeRenderEnabled && preferences.reviewAutoSelectStrongFaceEnabled) {
        startRequestPayload.review_options = {
          auto_select_strong_face_min_score_percent: normalizeReviewAutoSelectStrongFaceMinScorePercent(
            preferences.reviewAutoSelectStrongFaceMinScorePercent,
          ),
        };
      }

      const response = await fetch(`${apiUrl}/tasks/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          user_id: session.user.id,
        },
        body: JSON.stringify(startRequestPayload),
      });

      if (!response.ok) {
        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        throw new Error(responseData?.detail || `API error: ${response.status}`);
      }

      const result = await response.json();
      window.location.href = `/tasks/${result.task_id}`;
    } catch (submitError) {
      console.error("Error processing video:", submitError);
      setError(submitError instanceof Error ? submitError.message : "Failed to process video. Please try again.");
    } finally {
      setIsLoading(false);
      setProgress(0);
      setStatusMessage("");
      setFileName(null);
      fileRef.current = null;
      setUrl("");
      if (youtubeInputRef.current) {
        youtubeInputRef.current.value = "";
      }
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  if (isPending) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-4">
        <div className="space-y-4">
          <Skeleton className="h-4 w-32 mx-auto" />
          <Skeleton className="h-4 w-48 mx-auto" />
          <Skeleton className="h-4 w-24 mx-auto" />
        </div>
      </div>
    );
  }

  if (!session?.user) {
    return (
      <div className="min-h-screen bg-white">
        <div className="max-w-4xl mx-auto px-4 py-24">
          <div className="text-center mb-16">
            <h1 className="text-5xl font-bold text-black mb-4">MrglSnips</h1>
            <p className="text-lg text-gray-600 mb-8 max-w-2xl mx-auto">
              Professional video clipping platform powered by AI
            </p>

            <div className="flex gap-4 justify-center mb-16">
              <Link href="/sign-up">
                <Button size="lg" className="px-8 py-3">Get Started</Button>
              </Link>
              <Link href="/sign-in">
                <Button variant="outline" size="lg" className="px-8 py-3">Sign In</Button>
              </Link>
            </div>
          </div>

          <Separator className="my-16" />

          <div className="grid md:grid-cols-3 gap-8">
            <div className="text-center">
              <h3 className="text-lg font-semibold text-black mb-2">AI Analysis</h3>
              <p className="text-gray-600">Advanced content analysis for optimal clip extraction</p>
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-black mb-2">Fast Processing</h3>
              <p className="text-gray-600">Enterprise-grade infrastructure for rapid video processing</p>
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-black mb-2">Secure Platform</h3>
              <p className="text-gray-600">Enterprise security standards with private processing</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <div className="border-b bg-white">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-3">
              <Image src="/brand/logo.png" alt="MrglSnips logo" width={96} height={96} className="h-24 w-24 object-contain" />
              <h1 className="text-xl font-bold text-black">MrglSnips</h1>
            </div>

            <div className="flex items-center gap-2">
              <Link href="/list">
                <Button variant="outline" size="sm">All Generations</Button>
              </Link>
              <Link href="/settings" className="flex items-center gap-3 hover:bg-accent rounded-lg px-3 py-2 transition-colors cursor-pointer">
                <Avatar className="w-8 h-8">
                  <AvatarImage src={session.user.image || ""} />
                  <AvatarFallback className="bg-gray-100 text-black text-sm">
                    {session.user.name?.charAt(0) || session.user.email?.charAt(0) || "U"}
                  </AvatarFallback>
                </Avatar>
                <div className="hidden sm:block">
                  <p className="text-sm font-medium text-black">{session.user.name}</p>
                  <p className="text-xs text-gray-500">{session.user.email}</p>
                </div>
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-4xl mx-auto px-4 py-16">
        <div className="max-w-2xl mx-auto">
          {latestTask ? (
            <div className="mb-8">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-black">Latest Generation</h2>
                <Link href="/list">
                  <Button variant="ghost" size="sm" className="text-blue-600 hover:text-blue-700">
                    See All <ArrowRight className="w-4 h-4 ml-1" />
                  </Button>
                </Link>
              </div>

              <Card
                className="hover:shadow-md transition-shadow cursor-pointer"
                role="button"
                tabIndex={0}
                onClick={() => router.push(`/tasks/${latestTask.id}`)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    router.push(`/tasks/${latestTask.id}`);
                  }
                }}
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-lg font-semibold text-black mb-2 truncate">{latestTask.source_title}</h3>
                      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                        {latestTask.source_url ? (
                          isHttpUrl(latestTask.source_url) ? (
                            <a
                              href={latestTask.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              title={latestTask.source_url}
                              onClick={(event) => event.stopPropagation()}
                              className="inline-flex max-w-[22rem]"
                            >
                              <Badge variant="outline" className="max-w-full truncate normal-case">{latestTask.source_url}</Badge>
                            </a>
                          ) : (
                            <Badge variant="outline" className="max-w-[22rem] truncate normal-case" title={latestTask.source_url}>
                              {latestTask.source_url}
                            </Badge>
                          )
                        ) : (
                          <Badge variant="outline" className="normal-case">{formatSourceTypeLabel(latestTask.source_type)}</Badge>
                        )}
                        <span className="flex items-center gap-1">
                          <Clock className="w-4 h-4" />
                          {new Date(latestTask.created_at).toLocaleDateString()}
                        </span>
                        {(() => {
                          const runtimeSummary = getTaskRuntimeSummary(
                            latestTask.created_at,
                            latestTask.updated_at,
                            latestTask.status,
                            latestTask.runtime_info,
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
                        <span>{latestTask.clips_count} {latestTask.clips_count === 1 ? "clip" : "clips"}</span>
                      </div>
                    </div>
                    <div className="flex-shrink-0">
                      {latestTask.status === "completed" ? (
                        <Badge className="bg-green-100 text-green-800">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          Completed
                        </Badge>
                      ) : latestTask.status === "processing" ? (
                        <Badge className="bg-emerald-100 text-emerald-800">
                          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                          Processing
                        </Badge>
                      ) : latestTask.status === "awaiting_review" ? (
                        <Badge className="bg-amber-100 text-amber-800">Needs Review</Badge>
                      ) : (
                        <Badge variant="outline">{latestTask.status}</Badge>
                      )}
                    </div>
                  </div>
                  {(latestTask.status === "processing" || latestTask.status === "queued") && latestTask.progress_message ? (
                    <p className="mt-2 text-sm font-medium text-emerald-700">{latestTask.progress_message}</p>
                  ) : null}
                </CardContent>
              </Card>

              <Separator className="my-8" />
            </div>
          ) : null}

          {isLoadingLatest ? (
            <div className="mb-8">
              <Skeleton className="h-5 w-32 mb-4" />
              <Card>
                <CardContent className="p-6">
                  <Skeleton className="h-5 w-64 mb-2" />
                  <Skeleton className="h-4 w-48" />
                </CardContent>
              </Card>
              <Separator className="my-8" />
            </div>
          ) : null}

          <div className="mb-8">
            <h2 className="text-2xl font-bold text-black mb-2">Create Task</h2>
            <p className="text-gray-600">
              Start a new clip-generation task, pick a processing profile, and bias selection toward the moments you want.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label htmlFor="source-type" className="text-sm font-medium text-black">Source Type</label>
              <Select
                value={sourceType}
                onValueChange={(value: "youtube" | "upload") => {
                  setSourceType(value);
                  if (value === "youtube") {
                    setFileName(null);
                    fileRef.current = null;
                    if (fileInputRef.current) {
                      fileInputRef.current.value = "";
                    }
                  }
                }}
                disabled={isLoading}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select source type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="youtube">
                    <div className="flex items-center gap-2">
                      <Youtube className="w-4 h-4" />
                      YouTube URL
                    </div>
                  </SelectItem>
                  <SelectItem value="upload">
                    <div className="flex items-center gap-2">
                      <ArrowRight className="w-4 h-4" />
                      Upload Video
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {sourceType === "youtube" ? (
              <div key="source-youtube" className="space-y-2">
                <label htmlFor="youtube-url" className="text-sm font-medium text-black">YouTube URL</label>
                <Input
                  id="youtube-url"
                  type="url"
                  placeholder="https://www.youtube.com/watch?v=..."
                  ref={youtubeInputRef}
                  defaultValue=""
                  onChange={(event) => setUrl(event.target.value ?? "")}
                  disabled={isLoading}
                  className="h-11"
                />
              </div>
            ) : (
              <div key="source-upload" className="space-y-2">
                <label htmlFor="video-upload" className="text-sm font-medium text-black">Upload Video</label>
                <input
                  id="video-upload"
                  type="file"
                  data-slot="input"
                  accept="video/*"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  disabled={isLoading}
                  className="file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input flex h-11 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-base shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive"
                />
                {fileName ? <div className="text-xs text-gray-600 mt-1">Selected: {fileName}</div> : null}
              </div>
            )}

            <div className="space-y-4 rounded-lg border bg-gray-50 p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-medium text-black">Workflow</h3>
                  <p className="text-xs text-gray-600">
                    Workflows steer workflow, framing, and transcription defaults for this task only.
                  </p>
                </div>
                <Link href="/settings?section=workflow">
                  <Button type="button" variant="outline" size="sm">Edit Defaults</Button>
                </Link>
              </div>

              <Select
                value={getWorkflowSelectValue(selectedWorkflow)}
                onValueChange={(value) => setSelectedWorkflow(parseWorkflowSelectValue(value))}
                disabled={isLoading}
              >
                <SelectTrigger className="bg-white">
                  <SelectValue placeholder="Select workflow" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectLabel>Built-in</SelectLabel>
                    {Object.values(PROCESSING_PROFILE_PRESETS).map((profile) => (
                      <SelectItem key={profile.id} value={`built_in:${profile.id}`}>
                        {profile.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                  {savedWorkflows.length > 0 ? (
                    <SelectGroup>
                      <SelectLabel>Saved</SelectLabel>
                      {savedWorkflows.map((workflow) => (
                        <SelectItem key={workflow.id} value={`saved:${workflow.id}`}>
                          {workflow.name}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ) : null}
                  {selectedWorkflow.kind === "custom" ? (
                    <SelectGroup>
                      <SelectLabel>Current</SelectLabel>
                      <SelectItem value="custom">Custom</SelectItem>
                    </SelectGroup>
                  ) : null}
                </SelectContent>
              </Select>

              <div
                className={`rounded-lg border px-4 py-3 ${
                  selectedWorkflow.kind === "custom"
                    ? "border-amber-500 bg-amber-100"
                    : "border-dashed border-gray-300 bg-gray-50"
                }`}
              >
                <p
                  className={`text-xs font-medium uppercase tracking-wide ${
                    selectedWorkflow.kind === "custom" ? "text-amber-700" : "text-gray-500"
                  }`}
                >
                  Current workflow
                </p>
                <p className={`mt-1 text-sm font-semibold ${selectedWorkflow.kind === "custom" ? "text-amber-950" : "text-black"}`}>
                  {getWorkflowSelectionLabel(selectedWorkflow, savedWorkflows)}
                </p>
                <p className={`mt-1 text-xs ${selectedWorkflow.kind === "custom" ? "text-amber-900" : "text-gray-600"}`}>
                  {getWorkflowSelectionDescription(selectedWorkflow, savedWorkflows)}
                </p>
              </div>
            </div>

            <div className="space-y-4 rounded-lg border bg-gray-50 p-4">
              <div>
                <h3 className="text-sm font-medium text-black">Output format</h3>
                <p className="text-xs text-gray-600">
                  Choose the aspect ratio for this render. Auto keeps the source video shape.
                </p>
              </div>

              <Select
                value={selectedOutputAspectRatio}
                onValueChange={(value) => {
                  if (isOutputAspectRatio(value)) {
                    setSelectedOutputAspectRatio(value);
                  }
                }}
                disabled={isLoading}
              >
                <SelectTrigger className="bg-white">
                  <SelectValue placeholder="Select output format" />
                </SelectTrigger>
                <SelectContent>
                  {OUTPUT_ASPECT_RATIO_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label} · {option.description}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-4 rounded-lg border bg-gray-50 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-sm font-medium text-black">AI Focus Tags</h3>
                  <p className="text-xs text-gray-600">
                    Bias clip selection toward the kinds of moments you want. These are soft preferences, not hard filters.
                  </p>
                </div>
                <Badge variant="outline" className="shrink-0">
                  {aiFocusTags.length}/{MAX_AI_FOCUS_TAGS} selected
                </Badge>
              </div>

              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {AI_FOCUS_TAG_OPTIONS.map((option) => {
                  const isSelected = aiFocusTags.includes(option.value);
                  const atLimit = aiFocusTags.length >= MAX_AI_FOCUS_TAGS && !isSelected;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => toggleAiFocusTag(option.value)}
                      disabled={isLoading || atLimit}
                      className={[
                        "rounded-lg border px-3 py-3 text-left transition-colors",
                        isSelected
                          ? selectedOptionCardClass
                          : "border-gray-200 bg-white text-black hover:border-gray-400",
                        atLimit ? "cursor-not-allowed opacity-50" : "",
                      ].join(" ")}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium">{option.label}</span>
                        {isSelected ? <Badge className="bg-white text-black">On</Badge> : null}
                      </div>
                      <p className={`mt-1 text-xs ${isSelected ? "text-gray-200" : "text-gray-600"}`}>{option.description}</p>
                    </button>
                  );
                })}
              </div>

              {aiFocusTags.length > 0 ? (
                <div className="flex flex-wrap items-center gap-2">
                  {aiFocusTags.map((tag) => (
                    <Badge key={tag} variant="outline" className="bg-white">{formatAiFocusTag(tag)}</Badge>
                  ))}
                  <button
                    type="button"
                    onClick={() => setAiFocusTags([])}
                    disabled={isLoading}
                    className="text-xs text-gray-500 underline underline-offset-2"
                  >
                    Clear
                  </button>
                </div>
              ) : null}
            </div>

            <div className="rounded-lg border bg-white p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h3 className="text-sm font-medium text-black">Using Saved Defaults</h3>
                  <p className="text-xs text-gray-600">
                    This task will use your saved captions, framing, transcription, and AI defaults unless the selected profile overrides them.
                  </p>
                </div>
                <Link href="/settings">
                  <Button type="button" variant="ghost" size="sm">Edit in Settings</Button>
                </Link>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {summaryItems.map((item) => (
                  <div key={item.label} className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{item.label}</p>
                    <p className="mt-1 text-sm text-black">{item.value}</p>
                  </div>
                ))}
              </div>
            </div>

            {isLoading ? (
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">Upload</span>
                  <span className="text-black">{progress}%</span>
                </div>
                <Progress value={progress} className="h-2" />
                {statusMessage ? <p className="text-sm text-black">{statusMessage}</p> : null}
              </div>
            ) : null}

            {error ? (
              <Alert className="mt-6 border-red-200 bg-red-50">
                <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
              </Alert>
            ) : null}

            <Button
              type="submit"
              className="w-full h-11"
              disabled={
                (sourceType === "youtube" && !url.trim()) ||
                (sourceType === "upload" && !fileRef.current) ||
                isLoading
              }
            >
              {isLoading ? "Processing..." : "Process Video"}
            </Button>

            {((sourceType === "youtube" && url) || (sourceType === "upload" && fileName)) && !isLoading ? (
              <Alert className="mt-6">
                <AlertDescription className="text-sm">
                  Ready to process: {sourceType === "youtube" ? (url.length > 50 ? `${url.substring(0, 50)}...` : url) : fileName}
                </AlertDescription>
              </Alert>
            ) : null}
          </form>
        </div>
      </div>
    </div>
  );
}
