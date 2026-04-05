import { useEffect, useState, type ChangeEvent } from "react";
import { Cloud, Cpu } from "lucide-react";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  isSavingAssemblyKey: boolean;
  assemblyApiKey: string;
  hasSavedAssemblyKey: boolean;
  hasAssemblyEnvFallback: boolean;
  isSavingYoutubeCookies: boolean;
  hasSavedYoutubeCookies: boolean;
  hasYoutubeCookieEnvFallback: boolean;
  youtubeCookiesFilename: string | null;
  youtubeCookiesUpdatedAt: string | null;
  youtubeCookieSource: "saved" | "env" | "none";
  assemblyMaxDurationSeconds: number;
  assemblyMaxLocalUploadSizeBytes: number;
  assemblyKeyStatus: string | null;
  assemblyKeyError: string | null;
  youtubeCookieStatus: string | null;
  youtubeCookieError: string | null;
  onTranscriptionProviderChange: (provider: TranscriptionProvider) => void;
  onWhisperChunkingEnabledChange: (enabled: boolean) => void;
  onWhisperChunkDurationSecondsChange: (seconds: number) => void;
  onWhisperChunkOverlapSecondsChange: (seconds: number) => void;
  onTaskTimeoutSecondsChange: (seconds: number) => void;
  onWhisperPresetChange: (preset: Exclude<WhisperPresetId, "custom">) => void;
  onWhisperModelSizeChange: (modelSize: WhisperModelSize) => void;
  onWhisperDeviceChange: (device: WhisperDevicePreference) => void;
  onWhisperGpuIndexChange: (gpuIndex: number | null) => void;
  onAssemblyApiKeyChange: (value: string) => void;
  onSaveAssemblyKey: () => void;
  onDeleteAssemblyKey: () => void;
  onYoutubeCookiesUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onDeleteYoutubeCookies: () => void;
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
  isSavingAssemblyKey,
  assemblyApiKey,
  hasSavedAssemblyKey,
  hasAssemblyEnvFallback,
  isSavingYoutubeCookies,
  hasSavedYoutubeCookies,
  hasYoutubeCookieEnvFallback,
  youtubeCookiesFilename,
  youtubeCookiesUpdatedAt,
  youtubeCookieSource,
  assemblyMaxDurationSeconds,
  assemblyMaxLocalUploadSizeBytes,
  assemblyKeyStatus,
  assemblyKeyError,
  youtubeCookieStatus,
  youtubeCookieError,
  onTranscriptionProviderChange,
  onWhisperChunkingEnabledChange,
  onWhisperChunkDurationSecondsChange,
  onWhisperChunkOverlapSecondsChange,
  onTaskTimeoutSecondsChange,
  onWhisperPresetChange,
  onWhisperModelSizeChange,
  onWhisperDeviceChange,
  onWhisperGpuIndexChange,
  onAssemblyApiKeyChange,
  onSaveAssemblyKey,
  onDeleteAssemblyKey,
  onYoutubeCookiesUpload,
  onDeleteYoutubeCookies,
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

  const formatSizeGiB = (bytes: number): string => {
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return "unknown";
    }
    return `${(bytes / (1024 ** 3)).toFixed(2)} GiB`;
  };

  const formatHours = (seconds: number): string => {
    if (!Number.isFinite(seconds) || seconds <= 0) {
      return "unknown";
    }
    return `${(seconds / 3600).toFixed(1)}h`;
  };

  const formatSavedAt = (value: string | null): string | null => {
    if (!value) {
      return null;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(parsed);
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
      <div className="space-y-3">
        <div>
          <p className="text-sm font-medium text-black">Provider</p>
          <p className="text-xs text-gray-500">Choose local Whisper or AssemblyAI for transcript generation.</p>
        </div>

        <Select
          value={transcriptionProvider}
          onValueChange={(value) => onTranscriptionProviderChange(value as TranscriptionProvider)}
          disabled={isSaving || isSavingAssemblyKey}
        >
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
            ? "Local mode uses the local worker queue and can run in parallel across workers."
            : "AssemblyAI mode uses a dedicated single-worker queue to avoid overloading remote transcription jobs."}
        </p>

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
            disabled={isSaving || isSavingAssemblyKey}
          />
          <p className="text-xs text-gray-500">Maximum allowed by current worker config: {taskTimeoutMaxSeconds}s.</p>
        </div>

        {transcriptionProvider === "local" && (
          <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
            <div className="space-y-1">
              <label className="text-xs font-medium text-black">Local Whisper Preset</label>
              <Select
                value={whisperPreset}
                onValueChange={(value) => {
                  if (value !== "custom") {
                    onWhisperPresetChange(value as Exclude<WhisperPresetId, "custom">);
                  }
                }}
                disabled={isSaving || isSavingAssemblyKey}
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
                Presets are shortcuts. Editing the detailed local Whisper settings below switches the selection to
                Custom.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-medium text-black">Local Whisper Quality</label>
              <Select
                value={whisperModelSize}
                onValueChange={(value) => onWhisperModelSizeChange(value as WhisperModelSize)}
                disabled={isSaving || isSavingAssemblyKey}
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
              <p className="text-xs text-gray-500">
                This controls the local Whisper model used for future tasks. If that model is not cached yet, the first
                run will download it before transcription starts.
              </p>
              {selectedWhisperModel ? (
                <div className="flex flex-wrap gap-2 pt-1">
                  <Badge variant="outline" className="bg-white">
                    {selectedWhisperModel.speed_hint}
                  </Badge>
                  <Badge variant="outline" className="bg-white">
                    {selectedWhisperModel.quality_hint}
                  </Badge>
                  {selectedWhisperModel.approx_vram_hint ? (
                    <Badge variant="outline" className="bg-white">
                      {selectedWhisperModel.approx_vram_hint}
                    </Badge>
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

            <div className="space-y-1">
              <label className="text-xs font-medium text-black">Local Whisper Device</label>
              <Select
                value={whisperDevice}
                onValueChange={(value) => onWhisperDeviceChange(value as WhisperDevicePreference)}
                disabled={isSaving || isSavingAssemblyKey}
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
              <p className="text-xs text-gray-500">
                Auto mode checks GPU availability at transcription time inside the worker and prefers the GPU worker
                queue when that profile is enabled.
              </p>
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

            {whisperDevice !== "cpu" && (
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
                  disabled={isSaving || isSavingAssemblyKey}
                  placeholder="Leave blank to use the first available GPU"
                />
                <p className="text-xs text-gray-500">
                  Use `0` for the first GPU, `1` for the second, and so on.
                </p>
              </div>
            )}

            <label className="flex items-center gap-2 text-xs font-medium text-black">
              <input
                type="checkbox"
                checked={whisperChunkingEnabled}
                onChange={(event) => onWhisperChunkingEnabledChange(event.target.checked)}
                disabled={isSaving || isSavingAssemblyKey}
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
                  disabled={isSaving || isSavingAssemblyKey || !whisperChunkingEnabled}
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
                  disabled={isSaving || isSavingAssemblyKey || !whisperChunkingEnabled}
                />
              </div>
            </div>
            <p className="text-xs text-gray-500">
              Recommended defaults: 1200s duration with 8s overlap for multi-hour videos.
            </p>
          </div>
        )}

        <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
          <p className="text-xs font-medium text-black">Effective Runtime Target</p>
          <div className="grid gap-1 text-xs text-gray-600 sm:grid-cols-2">
            <p>
              <span className="font-medium text-black">Provider:</span> {runtimeSummary.providerLabel}
            </p>
            <p>
              <span className="font-medium text-black">Queue:</span>{" "}
              <Badge variant="outline" className="bg-white align-middle">
                {runtimeSummary.queueTarget}
              </Badge>
            </p>
            <p>
              <span className="font-medium text-black">Model:</span> {runtimeSummary.modelLabel}
            </p>
            <p>
              <span className="font-medium text-black">Device preference:</span> {runtimeSummary.devicePreferenceLabel}
            </p>
            <p>
              <span className="font-medium text-black">Predicted execution:</span> {runtimeSummary.executionTarget}
            </p>
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
          <p className="text-xs text-gray-500">
            Prediction is based on the current API runtime probe and queue routing config. Worker runtime can still
            differ.
          </p>
        </div>

        {transcriptionProvider === "assemblyai" && (
          <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
            <label htmlFor="assembly-api-key" className="text-xs font-medium text-black">
              AssemblyAI API Key
            </label>
            <Input
              id="assembly-api-key"
              type="password"
              value={assemblyApiKey}
              onChange={(event) => onAssemblyApiKeyChange(event.target.value ?? "")}
              placeholder={
                hasSavedAssemblyKey ? "Saved key present (enter new key to replace)" : "Paste your AssemblyAI key"
              }
              disabled={isSaving || isSavingAssemblyKey}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSaving || isSavingAssemblyKey || !assemblyApiKey.trim()}
                onClick={onSaveAssemblyKey}
              >
                {isSavingAssemblyKey ? "Saving..." : "Save Key"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={isSaving || isSavingAssemblyKey || !hasSavedAssemblyKey}
                onClick={onDeleteAssemblyKey}
              >
                Remove Saved Key
              </Button>
              <span className="text-xs text-gray-500">
                {hasSavedAssemblyKey
                  ? "Saved key available"
                  : hasAssemblyEnvFallback
                    ? "No saved key; using backend env fallback"
                    : "No key configured"}
              </span>
            </div>
            <p className="text-xs text-amber-700">
              AssemblyAI limits: max {formatSizeGiB(assemblyMaxLocalUploadSizeBytes)} for local file upload and{" "}
              {formatHours(assemblyMaxDurationSeconds)} audio duration. If exceeded, tasks automatically fall back to
              local Whisper.
            </p>
            {assemblyKeyStatus && <p className="text-xs text-green-600">{assemblyKeyStatus}</p>}
            {assemblyKeyError && <p className="text-xs text-red-600">{assemblyKeyError}</p>}
          </div>
        )}

        <div className="space-y-2 rounded border border-gray-100 bg-gray-50 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor="youtube-cookies-file" className="text-xs font-medium text-black">
              YouTube Cookies.txt
            </label>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button type="button" variant="ghost" size="sm" className="h-auto px-2 py-1 text-xs">
                  How to export cookies.txt
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Export YouTube cookies.txt</AlertDialogTitle>
                  <AlertDialogDescription>
                    Use a browser session where the target video already opens successfully.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <div className="space-y-3 text-sm text-slate-700">
                  <ol className="list-decimal space-y-2 pl-5">
                    <li>Open YouTube in the same browser profile you normally use, sign in, and confirm the video plays there.</li>
                    <li>Use a browser cookie export tool or extension that saves cookies in Netscape `cookies.txt` format.</li>
                    <li>Export the cookies without editing the file. The result should stay a plain `.txt` file and include `youtube.com` or `google.com` rows.</li>
                    <li>Upload that file here and retry the failed task from the `download` stage.</li>
                  </ol>
                  <div className="rounded border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    Re-export the file if YouTube signs you out, the browser session changes, or the upload still fails
                    with sign-in verification.
                  </div>
                </div>
                <AlertDialogFooter>
                  <AlertDialogCancel>Close</AlertDialogCancel>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
          <Input
            id="youtube-cookies-file"
            type="file"
            accept=".txt,text/plain"
            onChange={onYoutubeCookiesUpload}
            disabled={isSaving || isSavingAssemblyKey || isSavingYoutubeCookies}
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isSaving || isSavingAssemblyKey || isSavingYoutubeCookies || !hasSavedYoutubeCookies}
              onClick={onDeleteYoutubeCookies}
            >
              Remove Saved Cookies
            </Button>
            <span className="text-xs text-gray-500">
              {hasSavedYoutubeCookies
                ? `Saved${youtubeCookiesFilename ? `: ${youtubeCookiesFilename}` : ""}`
                : hasYoutubeCookieEnvFallback
                  ? "No saved cookies; shared server fallback available"
                  : "No YouTube cookies configured"}
            </span>
          </div>
          {youtubeCookiesUpdatedAt ? (
            <p className="text-xs text-gray-500">
              Last updated: {formatSavedAt(youtubeCookiesUpdatedAt) || youtubeCookiesUpdatedAt}
            </p>
          ) : null}
          <p className="text-xs text-gray-500">
            Use a Netscape-format YouTube `cookies.txt` export when YouTube blocks downloads with sign-in verification.
            Saved user cookies take precedence over the shared server fallback.
          </p>
          <p className="text-xs text-gray-500">
            Effective source: {youtubeCookieSource === "saved" ? "saved user cookies" : youtubeCookieSource === "env" ? "shared server fallback" : "none"}
          </p>
          {youtubeCookieStatus ? <p className="text-xs text-green-700">{youtubeCookieStatus}</p> : null}
          {youtubeCookieError ? <p className="text-xs text-red-700">{youtubeCookieError}</p> : null}
        </div>
      </div>
    </div>
  );
}
