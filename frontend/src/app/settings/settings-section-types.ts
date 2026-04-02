import {
  DEFAULT_FONT_STYLE_OPTIONS,
  normalizeFontSize,
  type FontStyleOptions,
} from "@/lib/font-style-options";

export const SETTINGS_SECTIONS = ["font", "video", "transcription", "ai"] as const;

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number];

export const TRANSCRIPTION_PROVIDERS = ["local", "assemblyai"] as const;
export const WHISPER_DEVICE_PREFERENCES = ["auto", "cpu", "gpu"] as const;
export const AI_PROVIDERS = ["openai", "google", "anthropic", "zai", "ollama"] as const;
export const ZAI_ROUTING_MODES = ["auto", "subscription", "metered"] as const;
export const OLLAMA_AUTH_MODES = ["none", "bearer", "custom_header"] as const;

export type TranscriptionProvider = (typeof TRANSCRIPTION_PROVIDERS)[number];
export type WhisperDevicePreference = (typeof WHISPER_DEVICE_PREFERENCES)[number];
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
  transcriptionProvider: TranscriptionProvider;
  whisperChunkingEnabled: boolean;
  whisperChunkDurationSeconds: number;
  whisperChunkOverlapSeconds: number;
  taskTimeoutSeconds: number;
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
  transcriptionProvider: "local",
  whisperChunkingEnabled: true,
  whisperChunkDurationSeconds: 1200,
  whisperChunkOverlapSeconds: 8,
  taskTimeoutSeconds: 21600,
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
  font: {
    label: "Fonts",
    description: "Subtitle style applied to new tasks.",
  },
  video: {
    label: "Video",
    description: "Clip composition and transitions for new tasks.",
  },
  transcription: {
    label: "Transcription",
    description: "Provider, chunking, timeout, and transcription API key.",
  },
  ai: {
    label: "AI",
    description: "LLM provider, model, provider API keys, and Ollama server settings.",
  },
};

export function isTranscriptionProvider(value: string): value is TranscriptionProvider {
  return TRANSCRIPTION_PROVIDERS.includes(value as TranscriptionProvider);
}

export function isWhisperDevicePreference(value: string): value is WhisperDevicePreference {
  return WHISPER_DEVICE_PREFERENCES.includes(value as WhisperDevicePreference);
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
    a.transitionsEnabled === b.transitionsEnabled &&
    a.reviewBeforeRenderEnabled === b.reviewBeforeRenderEnabled &&
    a.timelineEditorEnabled === b.timelineEditorEnabled &&
    a.transcriptionProvider === b.transcriptionProvider &&
    a.whisperChunkingEnabled === b.whisperChunkingEnabled &&
    a.whisperChunkDurationSeconds === b.whisperChunkDurationSeconds &&
    a.whisperChunkOverlapSeconds === b.whisperChunkOverlapSeconds &&
    a.taskTimeoutSeconds === b.taskTimeoutSeconds &&
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

export { normalizeFontSize };
