import { useEffect, useState } from "react";
import { Cloud, Cpu } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { TranscriptionProvider, WhisperDevicePreference, WhisperModelSize } from "../settings-section-types";
import {
  describeLocalWhisperModel,
  FALLBACK_LOCAL_WHISPER_MODELS,
  getMatchingWhisperPreset,
  getWhisperModelCacheLabel,
  getWhisperModelOption,
  getPredictedWhisperExecutionSummary,
  getWhisperPresetLabel,
  type LocalWhisperModelOption,
  type LocalWhisperRuntimeInfo,
  type WhisperPresetId,
} from "@/lib/whisper-transcription";

interface SettingsSectionTranscriptionProps {
  isSaving: boolean;
  transcriptionProvider: TranscriptionProvider;
  whisperChunkingEnabled: boolean;
  whisperChunkDurationSeconds: number;
  whisperChunkOverlapSeconds: number;
  taskTimeoutSeconds: number;
  taskTimeoutMaxSeconds: number;
  whisperModelSize: WhisperModelSize;
  whisperDevice: WhisperDevicePreference;
  whisperGpuIndex: number | null;
  localWhisperModels?: LocalWhisperModelOption[];
  localWhisperRuntime?: LocalWhisperRuntimeInfo | null;
  gpuWorkerEnabled: boolean;
  onTranscriptionProviderChange: (provider: TranscriptionProvider) => void;
  onWhisperChunkingEnabledChange: (enabled: boolean) => void;
  onWhisperChunkDurationSecondsChange: (seconds: number) => void;
  onWhisperChunkOverlapSecondsChange: (seconds: number) => void;
  onTaskTimeoutSecondsChange: (seconds: number) => void;
  onWhisperPresetChange: (preset: Exclude<WhisperPresetId, "custom">) => void;
  onWhisperModelSizeChange: (modelSize: WhisperModelSize) => void;
  onWhisperDeviceChange: (device: WhisperDevicePreference) => void;
  onWhisperGpuIndexChange: (gpuIndex: number | null) => void;
}

export function SettingsSectionTranscription({
  isSaving,
  transcriptionProvider,
  whisperChunkingEnabled,
  whisperChunkDurationSeconds,
  whisperChunkOverlapSeconds,
  taskTimeoutSeconds,
  taskTimeoutMaxSeconds,
  whisperModelSize,
  whisperDevice,
  whisperGpuIndex,
  localWhisperModels,
  localWhisperRuntime,
  gpuWorkerEnabled,
  onTranscriptionProviderChange,
  onWhisperChunkingEnabledChange,
  onWhisperChunkDurationSecondsChange,
  onWhisperChunkOverlapSecondsChange,
  onTaskTimeoutSecondsChange,
  onWhisperPresetChange,
  onWhisperModelSizeChange,
  onWhisperDeviceChange,
  onWhisperGpuIndexChange,
}: SettingsSectionTranscriptionProps) {
  const [taskTimeoutInput, setTaskTimeoutInput] = useState(String(taskTimeoutSeconds));
  const [chunkDurationInput, setChunkDurationInput] = useState(String(whisperChunkDurationSeconds));
  const [chunkOverlapInput, setChunkOverlapInput] = useState(String(whisperChunkOverlapSeconds));
  const [gpuIndexInput, setGpuIndexInput] = useState(whisperGpuIndex === null ? "" : String(whisperGpuIndex));

  useEffect(() => {
    setTaskTimeoutInput(String(taskTimeoutSeconds));
  }, [taskTimeoutSeconds]);

  useEffect(() => {
    setChunkDurationInput(String(whisperChunkDurationSeconds));
  }, [whisperChunkDurationSeconds]);

  useEffect(() => {
    setChunkOverlapInput(String(whisperChunkOverlapSeconds));
  }, [whisperChunkOverlapSeconds]);

  useEffect(() => {
    setGpuIndexInput(whisperGpuIndex === null ? "" : String(whisperGpuIndex));
  }, [whisperGpuIndex]);

  const commitTaskTimeoutInput = () => {
    const parsed = Number(taskTimeoutInput);
    if (!Number.isFinite(parsed)) {
      setTaskTimeoutInput(String(taskTimeoutSeconds));
      return;
    }
    onTaskTimeoutSecondsChange(parsed);
  };

  const commitChunkDurationInput = () => {
    const parsed = Number(chunkDurationInput);
    if (!Number.isFinite(parsed)) {
      setChunkDurationInput(String(whisperChunkDurationSeconds));
      return;
    }
    onWhisperChunkDurationSecondsChange(parsed);
  };

  const commitChunkOverlapInput = () => {
    const parsed = Number(chunkOverlapInput);
    if (!Number.isFinite(parsed)) {
      setChunkOverlapInput(String(whisperChunkOverlapSeconds));
      return;
    }
    onWhisperChunkOverlapSecondsChange(parsed);
  };

  const commitGpuIndexInput = () => {
    const trimmed = gpuIndexInput.trim();
    if (!trimmed) {
      onWhisperGpuIndexChange(null);
      return;
    }
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0 || !Number.isInteger(parsed)) {
      setGpuIndexInput(whisperGpuIndex === null ? "" : String(whisperGpuIndex));
      return;
    }
    onWhisperGpuIndexChange(parsed);
  };

  const detectedGpuDevices = Array.isArray(localWhisperRuntime?.gpu_devices) ? localWhisperRuntime.gpu_devices : [];
  const resolvedWhisperModels = localWhisperModels && localWhisperModels.length > 0 ? localWhisperModels : FALLBACK_LOCAL_WHISPER_MODELS;
  const selectedWhisperModel = getWhisperModelOption(resolvedWhisperModels, whisperModelSize);
  const whisperPreset = getMatchingWhisperPreset({
    whisperModelSize,
    whisperDevice,
    whisperGpuIndex,
    whisperChunkingEnabled,
    whisperChunkDurationSeconds,
    whisperChunkOverlapSeconds,
    runtimeInfo: localWhisperRuntime,
  });
  const runtimeSummary = getPredictedWhisperExecutionSummary({
    transcriptionProvider,
    whisperModelSize,
    whisperDevice,
    whisperGpuIndex,
    runtimeInfo: localWhisperRuntime,
    models: resolvedWhisperModels,
    gpuWorkerEnabled,
  });

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Provider</p>
          <p className="text-xs text-gray-500">Choose local Whisper or AssemblyAI for transcript generation.</p>
        </div>

        <Select value={transcriptionProvider} onValueChange={(value) => onTranscriptionProviderChange(value as TranscriptionProvider)} disabled={isSaving}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select provider" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="local">
              <div className="flex items-center gap-2">
                <Cpu className="w-4 h-4" />
                Local Whisper
              </div>
            </SelectItem>
            <SelectItem value="assemblyai">
              <div className="flex items-center gap-2">
                <Cloud className="w-4 h-4" />
                AssemblyAI
              </div>
            </SelectItem>
          </SelectContent>
        </Select>

        <p className="text-xs text-gray-500">
          {transcriptionProvider === "local"
            ? "Local mode uses the local worker queues and can take advantage of GPU workers when available."
            : "AssemblyAI mode uses the managed cloud transcription path and its saved key from Connections."}
        </p>
      </div>

      {transcriptionProvider === "local" ? (
        <>
          <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
            <div>
              <p className="text-sm font-medium text-black">Local Whisper preset</p>
              <p className="text-xs text-gray-500">Presets are shortcuts for the common local Whisper setups.</p>
            </div>
            <Select
              value={whisperPreset}
              onValueChange={(value) => {
                if (value !== "custom") {
                  onWhisperPresetChange(value as Exclude<WhisperPresetId, "custom">);
                }
              }}
              disabled={isSaving}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select preset" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="fast">{getWhisperPresetLabel("fast")}</SelectItem>
                <SelectItem value="balanced">{getWhisperPresetLabel("balanced")}</SelectItem>
                <SelectItem value="best-quality">{getWhisperPresetLabel("best-quality")}</SelectItem>
                <SelectItem value="cpu-safe">{getWhisperPresetLabel("cpu-safe")}</SelectItem>
                <SelectItem value="custom" disabled>
                  {getWhisperPresetLabel("custom")}
                </SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500">
              Editing the advanced local Whisper settings below automatically moves the visible preset to Custom.
            </p>
          </div>

          <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
            <div>
              <p className="text-sm font-medium text-black">Local Whisper quality</p>
              <p className="text-xs text-gray-500">This controls the local Whisper model used for future tasks.</p>
            </div>
            <Select
              value={whisperModelSize}
              onValueChange={(value) => onWhisperModelSizeChange(value as WhisperModelSize)}
              disabled={isSaving}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select Whisper model quality" />
              </SelectTrigger>
              <SelectContent>
                {resolvedWhisperModels.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {describeLocalWhisperModel(option)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {selectedWhisperModel ? (
              <div className="flex flex-wrap gap-2">
                <Badge variant="outline" className="bg-white">{selectedWhisperModel.speed_hint}</Badge>
                <Badge variant="outline" className="bg-white">{selectedWhisperModel.quality_hint}</Badge>
                {selectedWhisperModel.approx_vram_hint ? (
                  <Badge variant="outline" className="bg-white">{selectedWhisperModel.approx_vram_hint}</Badge>
                ) : null}
                <Badge
                  className={
                    selectedWhisperModel.cache_status === "cached"
                      ? "bg-green-100 text-green-800"
                      : selectedWhisperModel.cache_status === "not_cached"
                        ? "bg-amber-100 text-amber-800"
                        : "bg-gray-100 text-gray-700"
                  }
                >
                  {getWhisperModelCacheLabel(selectedWhisperModel.cache_status)}
                </Badge>
              </div>
            ) : null}
          </div>
        </>
      ) : null}

      <details className="rounded-md border border-gray-200 bg-white p-4">
        <summary className="cursor-pointer list-none text-sm font-medium text-black">
          Advanced transcription settings
        </summary>
        <div className="mt-4 space-y-4">
          <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
            <label className="text-xs font-medium text-black">Task Timeout (seconds)</label>
            <Input
              type="number"
              min={300}
              max={taskTimeoutMaxSeconds}
              step={1}
              value={taskTimeoutInput}
              onChange={(event) => setTaskTimeoutInput(event.target.value)}
              onBlur={commitTaskTimeoutInput}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.currentTarget.blur();
                }
              }}
              disabled={isSaving}
            />
            <p className="text-xs text-gray-500">Maximum allowed by current worker config: {taskTimeoutMaxSeconds}s.</p>
          </div>

          {transcriptionProvider === "local" ? (
            <div className="space-y-4 rounded border border-gray-100 bg-gray-50 p-3">
              <div className="space-y-1">
                <label className="text-xs font-medium text-black">Local Whisper Device</label>
                <Select
                  value={whisperDevice}
                  onValueChange={(value) => onWhisperDeviceChange(value as WhisperDevicePreference)}
                  disabled={isSaving}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select device mode" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="auto">Auto: prefer GPU, fall back to CPU</SelectItem>
                    <SelectItem value="cpu">CPU only</SelectItem>
                    <SelectItem value="gpu">GPU only, fall back to CPU if unavailable</SelectItem>
                  </SelectContent>
                </Select>
                {detectedGpuDevices.length > 0 ? (
                  <p className="text-xs text-gray-500">
                    Detected in this runtime: {detectedGpuDevices.map((device) => `GPU ${device.index} (${device.name})`).join(", ")}.
                  </p>
                ) : (
                  <p className="text-xs text-gray-500">
                    No GPUs were detected from the current API runtime probe. Worker runtime may differ.
                  </p>
                )}
              </div>

              {whisperDevice !== "cpu" ? (
                <div className="space-y-1">
                  <label className="text-xs font-medium text-black">Preferred GPU Index (optional)</label>
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    value={gpuIndexInput}
                    onChange={(event) => setGpuIndexInput(event.target.value)}
                    onBlur={commitGpuIndexInput}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.currentTarget.blur();
                      }
                    }}
                    disabled={isSaving}
                    placeholder="Leave blank to use the first available GPU"
                  />
                </div>
              ) : null}

              <label className="flex items-center gap-2 text-xs font-medium text-black">
                <input
                  type="checkbox"
                  checked={whisperChunkingEnabled}
                  onChange={(event) => onWhisperChunkingEnabledChange(event.target.checked)}
                  disabled={isSaving}
                />
                Enable local Whisper chunking
              </label>

              <div className="grid gap-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-black">Chunk Duration (seconds)</label>
                  <Input
                    type="number"
                    min={300}
                    max={3600}
                    step={1}
                    value={chunkDurationInput}
                    onChange={(event) => setChunkDurationInput(event.target.value)}
                    onBlur={commitChunkDurationInput}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.currentTarget.blur();
                      }
                    }}
                    disabled={isSaving || !whisperChunkingEnabled}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-black">Chunk Overlap (seconds)</label>
                  <Input
                    type="number"
                    min={0}
                    max={120}
                    step={1}
                    value={chunkOverlapInput}
                    onChange={(event) => setChunkOverlapInput(event.target.value)}
                    onBlur={commitChunkOverlapInput}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.currentTarget.blur();
                      }
                    }}
                    disabled={isSaving || !whisperChunkingEnabled}
                  />
                </div>
              </div>
            </div>
          ) : null}

          <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
            <p className="text-xs font-medium text-black">Effective Runtime Target</p>
            <div className="grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
              <p><span className="font-medium text-black">Provider:</span> {runtimeSummary.providerLabel}</p>
              <p>
                <span className="font-medium text-black">Queue:</span>{" "}
                <Badge variant="outline" className="bg-white align-middle">{runtimeSummary.queueTarget}</Badge>
              </p>
              <p><span className="font-medium text-black">Model:</span> {runtimeSummary.modelLabel}</p>
              <p><span className="font-medium text-black">Device preference:</span> {runtimeSummary.devicePreferenceLabel}</p>
              <p><span className="font-medium text-black">Predicted execution:</span> {runtimeSummary.executionTarget}</p>
              <p>
                <span className="font-medium text-black">Model cache:</span>{" "}
                <Badge
                  className={
                    runtimeSummary.cacheLabel === "Cached"
                      ? "bg-green-100 text-green-800 align-middle"
                      : runtimeSummary.cacheLabel === "Downloads on first use"
                        ? "bg-amber-100 text-amber-800 align-middle"
                        : "bg-gray-100 text-gray-700 align-middle"
                  }
                >
                  {runtimeSummary.cacheLabel}
                </Badge>
              </p>
            </div>
          </div>
        </div>
      </details>
    </div>
  );
}
