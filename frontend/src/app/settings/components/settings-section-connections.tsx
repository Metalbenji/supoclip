import { useEffect, useState, type ChangeEvent } from "react";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AiProvider, OllamaAuthMode, OllamaProfileSummary, ZaiRoutingMode } from "../settings-section-types";
import { AI_PROVIDERS, OLLAMA_AUTH_MODES } from "../settings-section-types";

interface SettingsSectionConnectionsProps {
  isSaving: boolean;
  defaultKeyProvider: AiProvider;
  aiApiKeys: Record<AiProvider, string>;
  hasSavedAiKeys: Record<AiProvider, boolean>;
  hasEnvAiFallback: Record<AiProvider, boolean>;
  isSavingAiKey: boolean;
  aiKeyStatus: string | null;
  aiKeyError: string | null;
  onAiApiKeyChange: (provider: AiProvider, value: string) => void;
  onSaveAiProviderKey: (provider: AiProvider) => void;
  onDeleteAiProviderKey: (provider: AiProvider) => void;
  selectedZaiKeyProfile: "subscription" | "metered";
  zaiRoutingMode: ZaiRoutingMode;
  zaiProfileApiKeys: Record<"subscription" | "metered", string>;
  hasSavedZaiProfileKeys: Record<"subscription" | "metered", boolean>;
  onSelectedZaiKeyProfileChange: (profile: "subscription" | "metered") => void;
  onZaiRoutingModeChange: (mode: ZaiRoutingMode) => void;
  onZaiProfileApiKeyChange: (profile: "subscription" | "metered", value: string) => void;
  onSaveZaiProfileKey: (profile: "subscription" | "metered") => void;
  onDeleteZaiProfileKey: (profile: "subscription" | "metered") => void;
  ollamaServerUrl: string;
  hasSavedOllamaServer: boolean;
  hasEnvOllamaServer: boolean;
  ollamaProfiles: OllamaProfileSummary[];
  selectedOllamaProfile: string;
  newOllamaProfileName: string;
  ollamaAuthMode: OllamaAuthMode;
  ollamaAuthHeaderName: string;
  ollamaAuthToken: string;
  ollamaTimeoutSeconds: number;
  ollamaMaxRetries: number;
  ollamaRetryBackoffMs: number;
  isTestingOllamaConnection: boolean;
  ollamaConnectionStatus: string | null;
  ollamaConnectionError: string | null;
  onOllamaServerUrlChange: (value: string) => void;
  onSelectedOllamaProfileChange: (value: string) => void;
  onNewOllamaProfileNameChange: (value: string) => void;
  onCreateOllamaProfile: () => void;
  onSaveOllamaProfile: () => void;
  onDeleteOllamaProfile: () => void;
  onSetDefaultOllamaProfile: () => void;
  onOllamaAuthModeChange: (value: OllamaAuthMode) => void;
  onOllamaAuthHeaderNameChange: (value: string) => void;
  onOllamaAuthTokenChange: (value: string) => void;
  onOllamaTimeoutSecondsChange: (value: number) => void;
  onOllamaMaxRetriesChange: (value: number) => void;
  onOllamaRetryBackoffMsChange: (value: number) => void;
  onSaveOllamaRequestControls: () => void;
  onTestOllamaConnection: () => void;
  isSavingAssemblyKey: boolean;
  assemblyApiKey: string;
  hasSavedAssemblyKey: boolean;
  hasAssemblyEnvFallback: boolean;
  assemblyMaxDurationSeconds: number;
  assemblyMaxLocalUploadSizeBytes: number;
  assemblyKeyStatus: string | null;
  assemblyKeyError: string | null;
  onAssemblyApiKeyChange: (value: string) => void;
  onSaveAssemblyKey: () => void;
  onDeleteAssemblyKey: () => void;
  isSavingYoutubeCookies: boolean;
  hasSavedYoutubeCookies: boolean;
  hasYoutubeCookieEnvFallback: boolean;
  youtubeCookiesFilename: string | null;
  youtubeCookiesUpdatedAt: string | null;
  youtubeCookieSource: "saved" | "env" | "none";
  youtubeCookieStatus: string | null;
  youtubeCookieError: string | null;
  onYoutubeCookiesUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onDeleteYoutubeCookies: () => void;
}

export function SettingsSectionConnections({
  isSaving,
  defaultKeyProvider,
  aiApiKeys,
  hasSavedAiKeys,
  hasEnvAiFallback,
  isSavingAiKey,
  aiKeyStatus,
  aiKeyError,
  onAiApiKeyChange,
  onSaveAiProviderKey,
  onDeleteAiProviderKey,
  selectedZaiKeyProfile,
  zaiRoutingMode,
  zaiProfileApiKeys,
  hasSavedZaiProfileKeys,
  onSelectedZaiKeyProfileChange,
  onZaiRoutingModeChange,
  onZaiProfileApiKeyChange,
  onSaveZaiProfileKey,
  onDeleteZaiProfileKey,
  ollamaServerUrl,
  hasSavedOllamaServer,
  hasEnvOllamaServer,
  ollamaProfiles,
  selectedOllamaProfile,
  newOllamaProfileName,
  ollamaAuthMode,
  ollamaAuthHeaderName,
  ollamaAuthToken,
  ollamaTimeoutSeconds,
  ollamaMaxRetries,
  ollamaRetryBackoffMs,
  isTestingOllamaConnection,
  ollamaConnectionStatus,
  ollamaConnectionError,
  onOllamaServerUrlChange,
  onSelectedOllamaProfileChange,
  onNewOllamaProfileNameChange,
  onCreateOllamaProfile,
  onSaveOllamaProfile,
  onDeleteOllamaProfile,
  onSetDefaultOllamaProfile,
  onOllamaAuthModeChange,
  onOllamaAuthHeaderNameChange,
  onOllamaAuthTokenChange,
  onOllamaTimeoutSecondsChange,
  onOllamaMaxRetriesChange,
  onOllamaRetryBackoffMsChange,
  onSaveOllamaRequestControls,
  onTestOllamaConnection,
  isSavingAssemblyKey,
  assemblyApiKey,
  hasSavedAssemblyKey,
  hasAssemblyEnvFallback,
  assemblyMaxDurationSeconds,
  assemblyMaxLocalUploadSizeBytes,
  assemblyKeyStatus,
  assemblyKeyError,
  onAssemblyApiKeyChange,
  onSaveAssemblyKey,
  onDeleteAssemblyKey,
  isSavingYoutubeCookies,
  hasSavedYoutubeCookies,
  hasYoutubeCookieEnvFallback,
  youtubeCookiesFilename,
  youtubeCookiesUpdatedAt,
  youtubeCookieSource,
  youtubeCookieStatus,
  youtubeCookieError,
  onYoutubeCookiesUpload,
  onDeleteYoutubeCookies,
}: SettingsSectionConnectionsProps) {
  const [selectedProvider, setSelectedProvider] = useState<AiProvider>(defaultKeyProvider);

  useEffect(() => {
    setSelectedProvider(defaultKeyProvider);
  }, [defaultKeyProvider]);

  const selectedProfileMeta = ollamaProfiles.find((profile) => profile.profile_name === selectedOllamaProfile) || null;

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

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">AI provider connections</p>
          <p className="text-xs text-gray-500">
            Save credentials and server configuration here. This does not change your default clip-selection provider.
          </p>
        </div>

        <Select value={selectedProvider} onValueChange={(value) => setSelectedProvider(value as AiProvider)} disabled={isSaving || isSavingAiKey}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select provider connection" />
          </SelectTrigger>
          <SelectContent>
            {AI_PROVIDERS.map((provider) => (
              <SelectItem key={provider} value={provider}>
                {provider === "zai"
                  ? "z.ai (GLM)"
                  : provider === "ollama"
                    ? "Ollama"
                    : provider.charAt(0).toUpperCase() + provider.slice(1)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selectedProvider === "zai" ? (
          <div className="space-y-3 rounded border border-gray-100 bg-gray-50 p-3">
            <label className="text-xs font-medium text-black">z.ai Key Routing</label>
            <Select
              value={zaiRoutingMode}
              onValueChange={(value) => onZaiRoutingModeChange(value as ZaiRoutingMode)}
              disabled={isSaving || isSavingAiKey}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select routing mode" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto (subscription then metered)</SelectItem>
                <SelectItem value="subscription">Subscription only</SelectItem>
                <SelectItem value="metered">Metered only</SelectItem>
              </SelectContent>
            </Select>
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-medium text-black">Profile to edit</label>
                <Select
                  value={selectedZaiKeyProfile}
                  onValueChange={(value) => onSelectedZaiKeyProfileChange(value as "subscription" | "metered")}
                  disabled={isSaving || isSavingAiKey}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select profile" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="subscription">Subscription</SelectItem>
                    <SelectItem value="metered">Metered</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-medium text-black">Saved profile keys</label>
                <p className="text-xs text-gray-600">
                  Subscription: {hasSavedZaiProfileKeys.subscription ? "yes" : "no"} | Metered: {hasSavedZaiProfileKeys.metered ? "yes" : "no"}
                </p>
              </div>
            </div>
            <Input
              type="password"
              value={zaiProfileApiKeys[selectedZaiKeyProfile]}
              onChange={(event) => onZaiProfileApiKeyChange(selectedZaiKeyProfile, event.target.value ?? "")}
              placeholder={`Paste your z.ai ${selectedZaiKeyProfile} key`}
              disabled={isSaving || isSavingAiKey}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSaving || isSavingAiKey || !zaiProfileApiKeys[selectedZaiKeyProfile].trim()}
                onClick={() => onSaveZaiProfileKey(selectedZaiKeyProfile)}
              >
                {isSavingAiKey ? "Saving..." : "Save Profile Key"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={
                  isSaving ||
                  isSavingAiKey ||
                  !hasSavedZaiProfileKeys[selectedZaiKeyProfile]
                }
                onClick={() => onDeleteZaiProfileKey(selectedZaiKeyProfile)}
              >
                Remove Profile Key
              </Button>
            </div>
            {aiKeyStatus ? <p className="text-xs text-green-600">{aiKeyStatus}</p> : null}
            {aiKeyError ? <p className="text-xs text-red-600">{aiKeyError}</p> : null}
          </div>
        ) : selectedProvider === "ollama" ? (
          <div className="space-y-3 rounded border border-gray-100 bg-gray-50 p-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-medium text-black">Profile</label>
                <Select
                  value={selectedOllamaProfile || "__none__"}
                  onValueChange={(value) => onSelectedOllamaProfileChange(value === "__none__" ? "" : value)}
                  disabled={isSaving || isSavingAiKey}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Select profile" />
                  </SelectTrigger>
                  <SelectContent>
                    {ollamaProfiles.length === 0 ? <SelectItem value="__none__">No saved profiles</SelectItem> : null}
                    {ollamaProfiles.map((profile) => (
                      <SelectItem key={profile.profile_name} value={profile.profile_name}>
                        {profile.profile_name}
                        {profile.is_default ? " (default)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={isSaving || isSavingAiKey || !selectedOllamaProfile || selectedProfileMeta?.is_default}
                  onClick={onSetDefaultOllamaProfile}
                >
                  Set Default
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={isSaving || isSavingAiKey || !selectedOllamaProfile}
                  onClick={onDeleteOllamaProfile}
                >
                  Delete Profile
                </Button>
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
              <Input
                value={newOllamaProfileName}
                onChange={(event) => onNewOllamaProfileNameChange(event.target.value ?? "")}
                placeholder="new profile name"
                disabled={isSaving || isSavingAiKey}
              />
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSaving || isSavingAiKey || !newOllamaProfileName.trim()}
                onClick={onCreateOllamaProfile}
              >
                Create Profile
              </Button>
            </div>

            <Input
              type="text"
              value={ollamaServerUrl}
              onChange={(event) => onOllamaServerUrlChange(event.target.value ?? "")}
              placeholder="http://localhost:11434"
              disabled={isSaving || isSavingAiKey}
            />

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-xs font-medium text-black">Auth Mode</label>
                <Select
                  value={ollamaAuthMode}
                  onValueChange={(value) => onOllamaAuthModeChange(value as OllamaAuthMode)}
                  disabled={isSaving || isSavingAiKey}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Auth mode" />
                  </SelectTrigger>
                  <SelectContent>
                    {OLLAMA_AUTH_MODES.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {mode}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {ollamaAuthMode === "custom_header" ? (
                <Input
                  value={ollamaAuthHeaderName}
                  onChange={(event) => onOllamaAuthHeaderNameChange(event.target.value ?? "")}
                  placeholder="X-API-Key"
                  disabled={isSaving || isSavingAiKey}
                />
              ) : null}
            </div>

            {ollamaAuthMode !== "none" ? (
              <Input
                type="password"
                value={ollamaAuthToken}
                onChange={(event) => onOllamaAuthTokenChange(event.target.value ?? "")}
                placeholder="Leave blank to keep existing token"
                disabled={isSaving || isSavingAiKey}
              />
            ) : null}

            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSaving || isSavingAiKey || !ollamaServerUrl.trim()}
                onClick={onSaveOllamaProfile}
              >
                {isSavingAiKey ? "Saving..." : "Save Profile"}
              </Button>
              <span className="text-xs text-gray-500">
                {hasSavedOllamaServer
                  ? `Saved profiles: ${ollamaProfiles.length}`
                  : hasEnvOllamaServer
                    ? "No saved profile; using backend env fallback"
                    : "No saved profile configured"}
              </span>
            </div>

            <details className="rounded border border-gray-200 bg-white p-3">
              <summary className="cursor-pointer list-none text-xs font-medium text-black">Advanced Ollama controls</summary>
              <div className="mt-3 space-y-3">
                <div className="grid gap-2 sm:grid-cols-3">
                  <Input
                    type="number"
                    min={1}
                    max={600}
                    value={String(ollamaTimeoutSeconds)}
                    onChange={(event) => onOllamaTimeoutSecondsChange(Number(event.target.value))}
                    disabled={isSaving || isSavingAiKey}
                    placeholder="Timeout (s)"
                  />
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    value={String(ollamaMaxRetries)}
                    onChange={(event) => onOllamaMaxRetriesChange(Number(event.target.value))}
                    disabled={isSaving || isSavingAiKey}
                    placeholder="Max retries"
                  />
                  <Input
                    type="number"
                    min={0}
                    max={30000}
                    value={String(ollamaRetryBackoffMs)}
                    onChange={(event) => onOllamaRetryBackoffMsChange(Number(event.target.value))}
                    disabled={isSaving || isSavingAiKey}
                    placeholder="Backoff (ms)"
                  />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Button type="button" variant="outline" size="sm" disabled={isSaving || isSavingAiKey} onClick={onSaveOllamaRequestControls}>
                    Save Request Controls
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={isSaving || isSavingAiKey || isTestingOllamaConnection}
                    onClick={onTestOllamaConnection}
                  >
                    {isTestingOllamaConnection ? "Testing..." : "Test Connection"}
                  </Button>
                </div>
              </div>
            </details>

            {ollamaConnectionStatus ? <p className="text-xs text-green-600">{ollamaConnectionStatus}</p> : null}
            {ollamaConnectionError ? <p className="text-xs text-red-600">{ollamaConnectionError}</p> : null}
            {aiKeyStatus ? <p className="text-xs text-green-600">{aiKeyStatus}</p> : null}
            {aiKeyError ? <p className="text-xs text-red-600">{aiKeyError}</p> : null}
          </div>
        ) : (
          <div className="space-y-3 rounded border border-gray-100 bg-gray-50 p-3">
            <Input
              type="password"
              value={aiApiKeys[selectedProvider]}
              onChange={(event) => onAiApiKeyChange(selectedProvider, event.target.value ?? "")}
              placeholder={
                hasSavedAiKeys[selectedProvider]
                  ? `Saved ${selectedProvider} key present (enter new key to replace)`
                  : `Paste your ${selectedProvider} API key`
              }
              disabled={isSaving || isSavingAiKey}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isSaving || isSavingAiKey || !aiApiKeys[selectedProvider].trim()}
                onClick={() => onSaveAiProviderKey(selectedProvider)}
              >
                {isSavingAiKey ? "Saving..." : "Save Key"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                disabled={isSaving || isSavingAiKey || !hasSavedAiKeys[selectedProvider]}
                onClick={() => onDeleteAiProviderKey(selectedProvider)}
              >
                Remove Saved Key
              </Button>
              <span className="text-xs text-gray-500">
                {hasSavedAiKeys[selectedProvider]
                  ? "Saved key available"
                  : hasEnvAiFallback[selectedProvider]
                    ? "No saved key; using backend env fallback"
                    : "No key configured"}
              </span>
            </div>
            {aiKeyStatus ? <p className="text-xs text-green-600">{aiKeyStatus}</p> : null}
            {aiKeyError ? <p className="text-xs text-red-600">{aiKeyError}</p> : null}
          </div>
        )}
      </div>

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">AssemblyAI</p>
          <p className="text-xs text-gray-500">Save the AssemblyAI key used when transcription provider is set to AssemblyAI.</p>
        </div>
        <Input
          type="password"
          value={assemblyApiKey}
          onChange={(event) => onAssemblyApiKeyChange(event.target.value ?? "")}
          placeholder={hasSavedAssemblyKey ? "Saved key present (enter new key to replace)" : "Paste your AssemblyAI key"}
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
          AssemblyAI limits: max {formatSizeGiB(assemblyMaxLocalUploadSizeBytes)} local upload and {formatHours(assemblyMaxDurationSeconds)} audio duration. Over-limit tasks fall back to local Whisper.
        </p>
        {assemblyKeyStatus ? <p className="text-xs text-green-600">{assemblyKeyStatus}</p> : null}
        {assemblyKeyError ? <p className="text-xs text-red-600">{assemblyKeyError}</p> : null}
      </div>

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-sm font-medium text-black">Download troubleshooting</p>
            <p className="text-xs text-gray-500">
              Use saved YouTube cookies when yt-dlp is blocked by sign-in verification. Saved user cookies take precedence over the shared server fallback.
            </p>
          </div>
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
                  <li>Upload that file here and retry the failed task from the download stage.</li>
                </ol>
              </div>
              <AlertDialogFooter>
                <AlertDialogCancel>Close</AlertDialogCancel>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>

        <Input
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
          Effective source: {youtubeCookieSource === "saved" ? "saved user cookies" : youtubeCookieSource === "env" ? "shared server fallback" : "none"}
        </p>
        {youtubeCookieStatus ? <p className="text-xs text-green-700">{youtubeCookieStatus}</p> : null}
        {youtubeCookieError ? <p className="text-xs text-red-700">{youtubeCookieError}</p> : null}
      </div>
    </div>
  );
}
