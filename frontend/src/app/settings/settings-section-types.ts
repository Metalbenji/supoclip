import {
  DEFAULT_FONT_STYLE_OPTIONS,
  normalizeFontSize,
  type FontStyleOptions,
} from "@/lib/font-style-options";

export const SETTINGS_SECTIONS = ["workflow", "captions", "framing", "transcription", "ai", "connections"] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export const TRANSCRIPTION_PROVIDERS = ["local", "assemblyai"] as const;
export const WHISPER_DEVICE_PREFERENCES = ["auto", "cpu", "gpu"] as const;
export const WHISPER_MODEL_SIZES = ["tiny", "base", "small", "medium", "large", "turbo"] as const;
export const DEFAULT_FRAMING_MODES = ["auto", "prefer_face", "fixed_position"] as const;
export const FACE_DETECTION_MODES = ["balanced", "more_faces"] as const;
export const FALLBACK_CROP_POSITIONS = ["center", "left_center", "right_center"] as const;
export const FACE_ANCHOR_PROFILES = [
  "auto",
  "left_only",
  "left_or_center",
  "center_only",
  "right_or_center",
  "right_only",
] as const;
export const OUTPUT_ASPECT_RATIOS = ["auto", "1:1", "21:9", "16:9", "9:16", "4:3", "4:5", "5:4", "3:4", "3:2", "2:3"] as const;
export const PROCESSING_PROFILES = ["fast_draft", "balanced", "best_quality", "stream_layout"] as const;
export const WORKFLOW_SOURCES = ["built_in", "saved", "custom"] as const;
export const AI_PROVIDERS = ["openai", "google", "anthropic", "zai", "ollama"] as const;
export const ZAI_ROUTING_MODES = ["auto", "subscription", "metered"] as const;
export const OLLAMA_AUTH_MODES = ["none", "bearer", "custom_header"] as const;

export type TranscriptionProvider = (typeof TRANSCRIPTION_PROVIDERS)[number];
export type WhisperDevicePreference = (typeof WHISPER_DEVICE_PREFERENCES)[number];
export type WhisperModelSize = (typeof WHISPER_MODEL_SIZES)[number];
export type DefaultFramingMode = (typeof DEFAULT_FRAMING_MODES)[number];
export type FaceDetectionMode = (typeof FACE_DETECTION_MODES)[number];
export type FallbackCropPosition = (typeof FALLBACK_CROP_POSITIONS)[number];
export type FaceAnchorProfile = (typeof FACE_ANCHOR_PROFILES)[number];
export type OutputAspectRatio = (typeof OUTPUT_ASPECT_RATIOS)[number];
export type ProcessingProfile = (typeof PROCESSING_PROFILES)[number];
export type PersistedProcessingProfile = ProcessingProfile | "custom";
export type WorkflowSource = (typeof WORKFLOW_SOURCES)[number];
export type AiProvider = (typeof AI_PROVIDERS)[number];
export type ZaiRoutingMode = (typeof ZAI_ROUTING_MODES)[number];
export type OllamaAuthMode = (typeof OLLAMA_AUTH_MODES)[number];

export interface OllamaProfileSummary {
  profile_name: string;
  base_url: string;
  auth_mode: OllamaAuthMode;
  auth_header_name?: string | null;
  enabled: boolean;
  is_default: boolean;
  has_auth_secret: boolean;
}

export interface OllamaRequestControls {
  timeout_seconds: number;
  max_retries: number;
  retry_backoff_ms: number;
}

export const DEFAULT_OLLAMA_REQUEST_CONTROLS: OllamaRequestControls = {
  timeout_seconds: 15,
  max_retries: 2,
  retry_backoff_ms: 400,
};

export const DEFAULT_REVIEW_AUTO_SELECT_STRONG_FACE_ENABLED = false;
export const DEFAULT_REVIEW_AUTO_SELECT_STRONG_FACE_MIN_SCORE_PERCENT = 85;
export const MIN_WHISPER_CHUNK_DURATION_SECONDS = 300;
export const MAX_WHISPER_CHUNK_DURATION_SECONDS = 3600;
export const MIN_WHISPER_CHUNK_OVERLAP_SECONDS = 0;
export const MAX_WHISPER_CHUNK_OVERLAP_SECONDS = 120;
export const MIN_TASK_TIMEOUT_SECONDS = 300;
export const MAX_TASK_TIMEOUT_SECONDS = 86400;

export interface UserPreferences extends FontStyleOptions {
  transitionsEnabled: boolean;
  reviewBeforeRenderEnabled: boolean;
  timelineEditorEnabled: boolean;
  defaultProcessingProfile: PersistedProcessingProfile;
  defaultWorkflowSource: WorkflowSource;
  defaultSavedWorkflowId: string | null;
  reviewAutoSelectStrongFaceEnabled: boolean;
  reviewAutoSelectStrongFaceMinScorePercent: number;
  defaultFramingMode: DefaultFramingMode;
  faceDetectionMode: FaceDetectionMode;
  fallbackCropPosition: FallbackCropPosition;
  faceAnchorProfile: FaceAnchorProfile;
  defaultOutputAspectRatio: OutputAspectRatio;
  transcriptionProvider: TranscriptionProvider;
  whisperChunkingEnabled: boolean;
  whisperChunkDurationSeconds: number;
  whisperChunkOverlapSeconds: number;
  taskTimeoutSeconds: number;
  whisperModelSize: WhisperModelSize;
  whisperDevice: WhisperDevicePreference;
  whisperGpuIndex: number | null;
  aiProvider: AiProvider;
  aiModel: string;
}

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  ...DEFAULT_FONT_STYLE_OPTIONS,
  transitionsEnabled: false,
  reviewBeforeRenderEnabled: true,
  timelineEditorEnabled: true,
  defaultProcessingProfile: "balanced",
  defaultWorkflowSource: "built_in",
  defaultSavedWorkflowId: null,
  reviewAutoSelectStrongFaceEnabled: DEFAULT_REVIEW_AUTO_SELECT_STRONG_FACE_ENABLED,
  reviewAutoSelectStrongFaceMinScorePercent: DEFAULT_REVIEW_AUTO_SELECT_STRONG_FACE_MIN_SCORE_PERCENT,
  defaultFramingMode: "auto",
  faceDetectionMode: "balanced",
  fallbackCropPosition: "center",
  faceAnchorProfile: "auto",
  defaultOutputAspectRatio: "9:16",
  transcriptionProvider: "local",
  whisperChunkingEnabled: true,
  whisperChunkDurationSeconds: 1200,
  whisperChunkOverlapSeconds: 8,
  taskTimeoutSeconds: 21600,
  whisperModelSize: "medium",
  whisperDevice: "auto",
  whisperGpuIndex: null,
  aiProvider: "openai",
  aiModel: "gpt-5",
};

export const DEFAULT_AI_MODELS: Record<AiProvider, string> = {
  openai: "gpt-5",
  google: "gemini-2.5-pro",
  anthropic: "claude-4-sonnet",
  zai: "glm-5",
  ollama: "gpt-oss:latest",
};

export const FALLBACK_AI_MODEL_OPTIONS: Record<AiProvider, string[]> = {
  openai: ["gpt-5", "gpt-5-mini", "gpt-4.1"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash"],
  anthropic: ["claude-4-sonnet", "claude-3-5-haiku"],
  zai: ["glm-5"],
  ollama: ["gpt-oss:latest", "qwen3:14b", "deepseek-r1:14b", "qwen3-vl:8b", "ministral-3:14b"],
};

export const SETTINGS_SECTION_META: Record<SettingsSection, { label: string; description: string }> = {
  workflow: {
    label: "Workflow",
    description: "Default task profile, review flow, and draft selection behavior.",
  },
  captions: {
    label: "Captions",
    description: "Subtitle style applied to new tasks.",
  },
  framing: {
    label: "Framing",
    description: "Output format, crop, and face-detection defaults for new tasks.",
  },
  transcription: {
    label: "Transcription",
    description: "Transcript provider and local Whisper defaults for future tasks.",
  },
  ai: {
    label: "AI",
    description: "Clip-selection provider and default model.",
  },
  connections: {
    label: "Connections",
    description: "Provider credentials, Ollama setup, and download troubleshooting.",
  },
};

export function isTranscriptionProvider(value: string): value is TranscriptionProvider {
  return TRANSCRIPTION_PROVIDERS.includes(value as TranscriptionProvider);
}

export function isWhisperDevicePreference(value: string): value is WhisperDevicePreference {
  return WHISPER_DEVICE_PREFERENCES.includes(value as WhisperDevicePreference);
}

export function isWhisperModelSize(value: string): value is WhisperModelSize {
  return WHISPER_MODEL_SIZES.includes(value as WhisperModelSize);
}

export function isDefaultFramingMode(value: string): value is DefaultFramingMode {
  return DEFAULT_FRAMING_MODES.includes(value as DefaultFramingMode);
}

export function isFaceDetectionMode(value: string): value is FaceDetectionMode {
  return FACE_DETECTION_MODES.includes(value as FaceDetectionMode);
}

export function isFallbackCropPosition(value: string): value is FallbackCropPosition {
  return FALLBACK_CROP_POSITIONS.includes(value as FallbackCropPosition);
}

export function isFaceAnchorProfile(value: string): value is FaceAnchorProfile {
  return FACE_ANCHOR_PROFILES.includes(value as FaceAnchorProfile);
}

export function isOutputAspectRatio(value: string): value is OutputAspectRatio {
  return OUTPUT_ASPECT_RATIOS.includes(value as OutputAspectRatio);
}

export function isProcessingProfile(value: string): value is ProcessingProfile {
  return PROCESSING_PROFILES.includes(value as ProcessingProfile);
}

export function isPersistedProcessingProfile(value: string): value is PersistedProcessingProfile {
  return value === "custom" || isProcessingProfile(value);
}

export function isWorkflowSource(value: string): value is WorkflowSource {
  return WORKFLOW_SOURCES.includes(value as WorkflowSource);
}

export function isAiProvider(value: string): value is AiProvider {
  return AI_PROVIDERS.includes(value as AiProvider);
}

export function isZaiRoutingMode(value: string): value is ZaiRoutingMode {
  return ZAI_ROUTING_MODES.includes(value as ZaiRoutingMode);
}

export function isSettingsSection(value: string | null): value is SettingsSection {
  return value !== null && SETTINGS_SECTIONS.includes(value as SettingsSection);
}

export function arePreferencesEqual(a: UserPreferences, b: UserPreferences): boolean {
  return (
    a.fontFamily === b.fontFamily &&
    a.fontSize === b.fontSize &&
    a.fontColor === b.fontColor &&
    a.highlightColor === b.highlightColor &&
    a.fontWeight === b.fontWeight &&
    a.lineHeight === b.lineHeight &&
    a.letterSpacing === b.letterSpacing &&
    a.textTransform === b.textTransform &&
    a.textAlign === b.textAlign &&
    a.strokeColor === b.strokeColor &&
    a.strokeWidth === b.strokeWidth &&
    a.strokeBlur === b.strokeBlur &&
    a.shadowColor === b.shadowColor &&
    a.shadowOpacity === b.shadowOpacity &&
    a.shadowBlur === b.shadowBlur &&
    a.shadowOffsetX === b.shadowOffsetX &&
    a.shadowOffsetY === b.shadowOffsetY &&
    a.dimUnhighlighted === b.dimUnhighlighted &&
    a.transitionsEnabled === b.transitionsEnabled &&
    a.reviewBeforeRenderEnabled === b.reviewBeforeRenderEnabled &&
    a.timelineEditorEnabled === b.timelineEditorEnabled &&
    a.defaultProcessingProfile === b.defaultProcessingProfile &&
    a.defaultWorkflowSource === b.defaultWorkflowSource &&
    a.defaultSavedWorkflowId === b.defaultSavedWorkflowId &&
    a.reviewAutoSelectStrongFaceEnabled === b.reviewAutoSelectStrongFaceEnabled &&
    a.reviewAutoSelectStrongFaceMinScorePercent === b.reviewAutoSelectStrongFaceMinScorePercent &&
    a.defaultFramingMode === b.defaultFramingMode &&
    a.faceDetectionMode === b.faceDetectionMode &&
    a.fallbackCropPosition === b.fallbackCropPosition &&
    a.faceAnchorProfile === b.faceAnchorProfile &&
    a.defaultOutputAspectRatio === b.defaultOutputAspectRatio &&
    a.transcriptionProvider === b.transcriptionProvider &&
    a.whisperChunkingEnabled === b.whisperChunkingEnabled &&
    a.whisperChunkDurationSeconds === b.whisperChunkDurationSeconds &&
    a.whisperChunkOverlapSeconds === b.whisperChunkOverlapSeconds &&
    a.taskTimeoutSeconds === b.taskTimeoutSeconds &&
    a.whisperModelSize === b.whisperModelSize &&
    a.whisperDevice === b.whisperDevice &&
    a.whisperGpuIndex === b.whisperGpuIndex &&
    a.aiProvider === b.aiProvider &&
    a.aiModel === b.aiModel
  );
}

export function normalizeWhisperChunkDurationSeconds(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.min(MAX_WHISPER_CHUNK_DURATION_SECONDS, Math.max(MIN_WHISPER_CHUNK_DURATION_SECONDS, Math.round(value)));
  }
  return DEFAULT_USER_PREFERENCES.whisperChunkDurationSeconds;
}

export function normalizeWhisperChunkOverlapSeconds(value: unknown, chunkDurationSeconds: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return DEFAULT_USER_PREFERENCES.whisperChunkOverlapSeconds;
  }
  const rounded = Math.round(value);
  const maxByDuration = Math.max(MIN_WHISPER_CHUNK_OVERLAP_SECONDS, chunkDurationSeconds - 1);
  const boundedMax = Math.min(MAX_WHISPER_CHUNK_OVERLAP_SECONDS, maxByDuration);
  return Math.min(boundedMax, Math.max(MIN_WHISPER_CHUNK_OVERLAP_SECONDS, rounded));
}

export function normalizeTaskTimeoutSeconds(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.min(MAX_TASK_TIMEOUT_SECONDS, Math.max(MIN_TASK_TIMEOUT_SECONDS, Math.round(value)));
  }
  return DEFAULT_USER_PREFERENCES.taskTimeoutSeconds;
}

export function normalizeReviewAutoSelectStrongFaceMinScorePercent(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.min(100, Math.max(0, Math.round(value)));
  }
  return DEFAULT_USER_PREFERENCES.reviewAutoSelectStrongFaceMinScorePercent;
}

export { normalizeFontSize };
