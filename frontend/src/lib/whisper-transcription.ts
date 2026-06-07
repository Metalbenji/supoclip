import type { TranscriptionProvider, WhisperDevicePreference, WhisperModelSize } from "@/app/settings/settings-section-types";

export type WhisperModelCacheStatus = "cached" | "not_cached" | "unknown";
export type WhisperPresetId = "fast" | "balanced" | "best-quality" | "cpu-safe" | "custom";

export interface WhisperGpuDeviceSummary {
  index: number;
  name: string;
  total_memory_bytes?: number | null;
}

export interface LocalWhisperRuntimeInfo {
  cuda_available?: boolean;
  gpu_devices?: WhisperGpuDeviceSummary[];
  probe_source?: string;
  runtime_scope?: string;
  cache_dir?: string;
}

export interface LocalWhisperModelOption {
  value: WhisperModelSize;
  label: string;
  speed_hint: string;
  quality_hint: string;
  approx_vram_hint?: string | null;
  cache_status?: WhisperModelCacheStatus | string | null;
}

export const DEFAULT_WHISPER_PRESET_CHUNK_DURATION_SECONDS = 1200;
export const DEFAULT_WHISPER_PRESET_CHUNK_OVERLAP_SECONDS = 8;

export const FALLBACK_LOCAL_WHISPER_MODELS: LocalWhisperModelOption[] = [
  {
    value: "turbo",
    label: "Turbo",
    speed_hint: "Fastest high-quality",
    quality_hint: "High quality",
    approx_vram_hint: "~6 GB VRAM",
    cache_status: "unknown",
  },
  {
    value: "medium",
    label: "Medium",
    speed_hint: "Balanced",
    quality_hint: "Balanced quality",
    approx_vram_hint: "~5 GB VRAM",
    cache_status: "unknown",
  },
  {
    value: "large",
    label: "Large",
    speed_hint: "Slowest",
    quality_hint: "Best quality",
    approx_vram_hint: "~10 GB VRAM",
    cache_status: "unknown",
  },
  {
    value: "small",
    label: "Small",
    speed_hint: "Faster",
    quality_hint: "Lower quality",
    approx_vram_hint: "~2 GB VRAM",
    cache_status: "unknown",
  },
  {
    value: "base",
    label: "Base",
    speed_hint: "Lightweight fallback",
    quality_hint: "Basic quality",
    approx_vram_hint: "Low VRAM",
    cache_status: "unknown",
  },
  {
    value: "tiny",
    label: "Tiny",
    speed_hint: "Smallest fallback",
    quality_hint: "Lowest quality",
    approx_vram_hint: "Low VRAM",
    cache_status: "unknown",
  },
];

const PRESET_DISPLAY_LABELS: Record<Exclude<WhisperPresetId, "custom">, string> = {
  fast: "Fast",
  balanced: "Balanced",
  "best-quality": "Best quality",
  "cpu-safe": "CPU-safe",
};

export function getWhisperPresetLabel(preset: WhisperPresetId): string {
  if (preset === "custom") {
    return "Custom";
  }
  return PRESET_DISPLAY_LABELS[preset];
}

export function getWhisperModelCacheLabel(cacheStatus: string | null | undefined): string {
  if (cacheStatus === "cached") {
    return "Cached";
  }
  if (cacheStatus === "not_cached") {
    return "Downloads on first use";
  }
  return "Cache status unknown";
}

export function describeLocalWhisperModel(option: LocalWhisperModelOption): string {
  const parts = [option.label, option.speed_hint, option.quality_hint];
  if (option.approx_vram_hint) {
    parts.push(option.approx_vram_hint);
  }
  parts.push(getWhisperModelCacheLabel(option.cache_status));
  return parts.join(" · ");
}

export function resolveWhisperPresetValues(
  preset: Exclude<WhisperPresetId, "custom">,
  runtimeInfo?: LocalWhisperRuntimeInfo | null,
): {
  whisperModelSize: WhisperModelSize;
  whisperDevice: WhisperDevicePreference;
  whisperGpuIndex: number | null;
  whisperChunkingEnabled: true;
  whisperChunkDurationSeconds: number;
  whisperChunkOverlapSeconds: number;
} {
  const hasDetectedGpu =
    Boolean(runtimeInfo?.cuda_available) ||
    (Array.isArray(runtimeInfo?.gpu_devices) && runtimeInfo.gpu_devices.length > 0);

  if (preset === "fast") {
    return {
      whisperModelSize: "turbo",
      whisperDevice: "auto",
      whisperGpuIndex: null,
      whisperChunkingEnabled: true,
      whisperChunkDurationSeconds: DEFAULT_WHISPER_PRESET_CHUNK_DURATION_SECONDS,
      whisperChunkOverlapSeconds: DEFAULT_WHISPER_PRESET_CHUNK_OVERLAP_SECONDS,
    };
  }
  if (preset === "balanced") {
    return {
      whisperModelSize: "medium",
      whisperDevice: "auto",
      whisperGpuIndex: null,
      whisperChunkingEnabled: true,
      whisperChunkDurationSeconds: DEFAULT_WHISPER_PRESET_CHUNK_DURATION_SECONDS,
      whisperChunkOverlapSeconds: DEFAULT_WHISPER_PRESET_CHUNK_OVERLAP_SECONDS,
    };
  }
  if (preset === "best-quality") {
    return {
      whisperModelSize: "large",
      whisperDevice: hasDetectedGpu ? "gpu" : "auto",
      whisperGpuIndex: null,
      whisperChunkingEnabled: true,
      whisperChunkDurationSeconds: DEFAULT_WHISPER_PRESET_CHUNK_DURATION_SECONDS,
      whisperChunkOverlapSeconds: DEFAULT_WHISPER_PRESET_CHUNK_OVERLAP_SECONDS,
    };
  }
  return {
    whisperModelSize: "small",
    whisperDevice: "cpu",
    whisperGpuIndex: null,
    whisperChunkingEnabled: true,
    whisperChunkDurationSeconds: DEFAULT_WHISPER_PRESET_CHUNK_DURATION_SECONDS,
    whisperChunkOverlapSeconds: DEFAULT_WHISPER_PRESET_CHUNK_OVERLAP_SECONDS,
  };
}

export function getMatchingWhisperPreset(params: {
  whisperModelSize: WhisperModelSize;
  whisperDevice: WhisperDevicePreference;
  whisperGpuIndex: number | null;
  whisperChunkingEnabled: boolean;
  whisperChunkDurationSeconds: number;
  whisperChunkOverlapSeconds: number;
  runtimeInfo?: LocalWhisperRuntimeInfo | null;
}): WhisperPresetId {
  const presetIds: Array<Exclude<WhisperPresetId, "custom">> = ["fast", "balanced", "best-quality", "cpu-safe"];
  for (const preset of presetIds) {
    const resolved = resolveWhisperPresetValues(preset, params.runtimeInfo);
    if (
      params.whisperModelSize === resolved.whisperModelSize &&
      params.whisperDevice === resolved.whisperDevice &&
      params.whisperGpuIndex === resolved.whisperGpuIndex &&
      params.whisperChunkingEnabled === resolved.whisperChunkingEnabled &&
      params.whisperChunkDurationSeconds === resolved.whisperChunkDurationSeconds &&
      params.whisperChunkOverlapSeconds === resolved.whisperChunkOverlapSeconds
    ) {
      return preset;
    }
  }
  return "custom";
}

export function getWhisperModelOption(
  models: LocalWhisperModelOption[] | undefined,
  value: WhisperModelSize,
): LocalWhisperModelOption | undefined {
  return models?.find((model) => model.value === value) ?? FALLBACK_LOCAL_WHISPER_MODELS.find((model) => model.value === value);
}

export function getPredictedWhisperExecutionSummary(params: {
  transcriptionProvider: TranscriptionProvider;
  whisperModelSize: WhisperModelSize;
  whisperDevice: WhisperDevicePreference;
  whisperGpuIndex: number | null;
  runtimeInfo?: LocalWhisperRuntimeInfo | null;
  models?: LocalWhisperModelOption[];
  gpuWorkerEnabled: boolean;
}): {
  providerLabel: string;
  queueTarget: string;
  executionTarget: string;
  cacheLabel: string;
  modelLabel: string;
  devicePreferenceLabel: string;
} {
  const selectedModel = getWhisperModelOption(params.models, params.whisperModelSize);
  const modelLabel = selectedModel ? selectedModel.label : params.whisperModelSize;
  const cacheLabel = selectedModel ? getWhisperModelCacheLabel(selectedModel.cache_status) : "Cache status unknown";
  const devicePreferenceLabel =
    params.whisperDevice === "cpu"
      ? "CPU only"
      : params.whisperDevice === "gpu"
        ? "GPU requested"
        : "Auto";

  if (params.transcriptionProvider === "assemblyai") {
    return {
      providerLabel: "AssemblyAI",
      queueTarget: "assembly",
      executionTarget: "Remote transcription",
      cacheLabel: "N/A",
      modelLabel,
      devicePreferenceLabel: "N/A",
    };
  }

  const availableGpuDevices = Array.isArray(params.runtimeInfo?.gpu_devices) ? params.runtimeInfo.gpu_devices : [];
  const preferredGpu =
    params.whisperGpuIndex === null
      ? availableGpuDevices[0]
      : availableGpuDevices.find((device) => device.index === params.whisperGpuIndex) ?? availableGpuDevices[0];
  const queueTarget = params.whisperDevice === "cpu" ? "local" : params.gpuWorkerEnabled ? "local-gpu" : "local";

  if (params.whisperDevice === "cpu") {
    return {
      providerLabel: "Local Whisper",
      queueTarget,
      executionTarget: "CPU",
      cacheLabel,
      modelLabel,
      devicePreferenceLabel,
    };
  }

  if (params.whisperDevice === "gpu") {
    return {
      providerLabel: "Local Whisper",
      queueTarget,
      executionTarget: preferredGpu
        ? `GPU ${preferredGpu.index} (${preferredGpu.name})`
        : "GPU requested, CPU fallback if unavailable",
      cacheLabel,
      modelLabel,
      devicePreferenceLabel,
    };
  }

  return {
    providerLabel: "Local Whisper",
    queueTarget,
    executionTarget: preferredGpu
      ? `GPU ${preferredGpu.index} (${preferredGpu.name}) if worker runtime matches probe`
      : params.gpuWorkerEnabled
        ? "GPU preferred if available, otherwise CPU"
        : "CPU unless a worker GPU is available",
    cacheLabel,
    modelLabel,
    devicePreferenceLabel,
  };
}
