"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Settings } from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useSession } from "@/lib/auth-client";
import { SettingsSaveStatus } from "./components/settings-save-status";
import { SettingsSectionAi } from "./components/settings-section-ai";
import { SettingsSectionFont } from "./components/settings-section-font";
import { SettingsSectionTranscription } from "./components/settings-section-transcription";
import { SettingsSectionVideo } from "./components/settings-section-video";
import { SettingsSidebar } from "./components/settings-sidebar";
import {
  FALLBACK_LOCAL_WHISPER_MODELS,
  resolveWhisperPresetValues,
  type LocalWhisperModelOption,
  type LocalWhisperRuntimeInfo,
  type WhisperPresetId,
} from "@/lib/whisper-transcription";
import {
  normalizeFontStyleOptions,
  normalizeFontWeight,
  normalizeLetterSpacing,
  normalizeLineHeight,
  normalizeShadowBlur,
  normalizeShadowOffset,
  normalizeShadowOpacity,
  normalizeStrokeBlur,
  normalizeStrokeWidth,
  type TextAlignOption,
  type TextTransformOption,
} from "@/lib/font-style-options";
import {
  arePreferencesEqual,
  DEFAULT_AI_MODELS,
  DEFAULT_OLLAMA_REQUEST_CONTROLS,
  DEFAULT_USER_PREFERENCES,
  FALLBACK_AI_MODEL_OPTIONS,
  isAiProvider,
  isSettingsSection,
  isTranscriptionProvider,
  isWhisperDevicePreference,
  isWhisperModelSize,
  isZaiRoutingMode,
  normalizeTaskTimeoutSeconds,
  normalizeFontSize,
  normalizeWhisperChunkDurationSeconds,
  normalizeWhisperChunkOverlapSeconds,
  SETTINGS_SECTION_META,
  SETTINGS_SECTIONS,
  MAX_TASK_TIMEOUT_SECONDS,
  type AiProvider,
  type OllamaAuthMode,
  type OllamaProfileSummary,
  type SettingsSection,
  type UserPreferences,
  type ZaiRoutingMode,
} from "./settings-section-types";

interface SavePreferencesOptions {
  keepalive?: boolean;
}

function getActiveSection(sectionValue: string | null): SettingsSection {
  if (sectionValue === "processing") {
    return "transcription";
  }
  return isSettingsSection(sectionValue) ? sectionValue : "font";
}

function SettingsPageContent() {
  const [preferencesDraft, setPreferencesDraft] = useState<UserPreferences>(DEFAULT_USER_PREFERENCES);
  const [lastSavedSnapshot, setLastSavedSnapshot] = useState<UserPreferences>(DEFAULT_USER_PREFERENCES);

  const [availableFonts, setAvailableFonts] = useState<Array<{ name: string; display_name: string }>>([]);
  const [isUploadingFont, setIsUploadingFont] = useState(false);
  const [fontUploadMessage, setFontUploadMessage] = useState<string | null>(null);
  const [fontUploadError, setFontUploadError] = useState<string | null>(null);

  const [isFetching, setIsFetching] = useState(true);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [assemblyApiKey, setAssemblyApiKey] = useState("");
  const [hasSavedAssemblyKey, setHasSavedAssemblyKey] = useState(false);
  const [hasAssemblyEnvFallback, setHasAssemblyEnvFallback] = useState(false);
  const [assemblyMaxDurationSeconds, setAssemblyMaxDurationSeconds] = useState(10 * 60 * 60);
  const [assemblyMaxLocalUploadSizeBytes, setAssemblyMaxLocalUploadSizeBytes] = useState(
    Math.floor(2.2 * 1024 * 1024 * 1024),
  );
  const [workerTimeoutCapSeconds, setWorkerTimeoutCapSeconds] = useState(MAX_TASK_TIMEOUT_SECONDS);
  const [localWhisperRuntime, setLocalWhisperRuntime] = useState<LocalWhisperRuntimeInfo | null>(null);
  const [localWhisperModels, setLocalWhisperModels] = useState<LocalWhisperModelOption[]>(FALLBACK_LOCAL_WHISPER_MODELS);
  const [gpuWorkerEnabled, setGpuWorkerEnabled] = useState(false);
  const [isSavingAssemblyKey, setIsSavingAssemblyKey] = useState(false);
  const [assemblyKeyStatus, setAssemblyKeyStatus] = useState<string | null>(null);
  const [assemblyKeyError, setAssemblyKeyError] = useState<string | null>(null);

  const [aiApiKeys, setAiApiKeys] = useState<Record<AiProvider, string>>({
    openai: "",
    google: "",
    anthropic: "",
    zai: "",
    ollama: "",
  });
  const [ollamaServerUrl, setOllamaServerUrl] = useState("http://localhost:11434");
  const [hasSavedOllamaServer, setHasSavedOllamaServer] = useState(false);
  const [hasEnvOllamaServer, setHasEnvOllamaServer] = useState(false);
  const [ollamaProfiles, setOllamaProfiles] = useState<OllamaProfileSummary[]>([]);
  const [selectedOllamaProfile, setSelectedOllamaProfile] = useState("");
  const [newOllamaProfileName, setNewOllamaProfileName] = useState("");
  const [ollamaAuthMode, setOllamaAuthMode] = useState<OllamaAuthMode>("none");
  const [ollamaAuthHeaderName, setOllamaAuthHeaderName] = useState("");
  const [ollamaAuthToken, setOllamaAuthToken] = useState("");
  const [ollamaRequestControls, setOllamaRequestControls] = useState(DEFAULT_OLLAMA_REQUEST_CONTROLS);
  const [isTestingOllamaConnection, setIsTestingOllamaConnection] = useState(false);
  const [ollamaConnectionStatus, setOllamaConnectionStatus] = useState<string | null>(null);
  const [ollamaConnectionError, setOllamaConnectionError] = useState<string | null>(null);
  const [zaiProfileApiKeys, setZaiProfileApiKeys] = useState<Record<"subscription" | "metered", string>>({
    subscription: "",
    metered: "",
  });
  const [hasSavedZaiProfileKeys, setHasSavedZaiProfileKeys] = useState<Record<"subscription" | "metered", boolean>>({
    subscription: false,
    metered: false,
  });
  const [selectedZaiKeyProfile, setSelectedZaiKeyProfile] = useState<"subscription" | "metered">("subscription");
  const [zaiRoutingMode, setZaiRoutingMode] = useState<ZaiRoutingMode>("auto");
  const [hasSavedAiKeys, setHasSavedAiKeys] = useState<Record<AiProvider, boolean>>({
    openai: false,
    google: false,
    anthropic: false,
    zai: false,
    ollama: false,
  });
  const [hasEnvAiFallback, setHasEnvAiFallback] = useState<Record<AiProvider, boolean>>({
    openai: false,
    google: false,
    anthropic: false,
    zai: false,
    ollama: false,
  });
  const [isSavingAiKey, setIsSavingAiKey] = useState(false);
  const [aiKeyStatus, setAiKeyStatus] = useState<string | null>(null);
  const [aiKeyError, setAiKeyError] = useState<string | null>(null);

  const [aiModelOptions, setAiModelOptions] = useState<Record<AiProvider, string[]>>({
    openai: FALLBACK_AI_MODEL_OPTIONS.openai,
    google: FALLBACK_AI_MODEL_OPTIONS.google,
    anthropic: FALLBACK_AI_MODEL_OPTIONS.anthropic,
    zai: FALLBACK_AI_MODEL_OPTIONS.zai,
    ollama: FALLBACK_AI_MODEL_OPTIONS.ollama,
  });
  const [hasLoadedAiModels, setHasLoadedAiModels] = useState<Record<AiProvider, boolean>>({
    openai: false,
    google: false,
    anthropic: false,
    zai: false,
    ollama: false,
  });
  const [isLoadingAiModels, setIsLoadingAiModels] = useState(false);
  const [aiModelStatus, setAiModelStatus] = useState<string | null>(null);
  const [aiModelError, setAiModelError] = useState<string | null>(null);

  const activeAiProviderRef = useRef<AiProvider>(preferencesDraft.aiProvider);
  const latestAiModelsRequestRef = useRef(0);
  const ollamaAutoEnsurePromptedRef = useRef<string | null>(null);
  const ollamaAutoEnsureInFlightRef = useRef(false);

  const { data: session, isPending } = useSession();
  const router = useRouter();
  const searchParams = useSearchParams();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const activeSection = getActiveSection(searchParams.get("section"));
  const isDirty = useMemo(
    () => !arePreferencesEqual(preferencesDraft, lastSavedSnapshot),
    [preferencesDraft, lastSavedSnapshot],
  );

  const hasAiKeyForSelectedProvider =
    preferencesDraft.aiProvider === "zai"
      ? hasSavedAiKeys.zai ||
        hasSavedZaiProfileKeys.subscription ||
        hasSavedZaiProfileKeys.metered ||
        hasEnvAiFallback.zai
      : preferencesDraft.aiProvider === "ollama"
        ? Boolean(ollamaServerUrl.trim()) || hasEnvOllamaServer || ollamaProfiles.length > 0
      : hasSavedAiKeys[preferencesDraft.aiProvider] || hasEnvAiFallback[preferencesDraft.aiProvider];

  const sectionNavItems = useMemo(
    () => SETTINGS_SECTIONS.map((section) => ({ id: section, ...SETTINGS_SECTION_META[section] })),
    [],
  );
  const selectedOllamaProfileMeta = useMemo(
    () => ollamaProfiles.find((profile) => profile.profile_name === selectedOllamaProfile) || null,
    [ollamaProfiles, selectedOllamaProfile],
  );

  const loadFonts = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/fonts`);
      if (!response.ok) {
        return;
      }

      const data = await response.json();
      const fonts = data.fonts || [];
      setAvailableFonts(fonts);

      const fontFaceStyles = fonts
        .map((font: { name: string }) => {
          return `
            @font-face {
              font-family: '${font.name}';
              src: url('${apiUrl}/fonts/${font.name}') format('truetype');
              font-weight: normal;
              font-style: normal;
            }
          `;
        })
        .join("\n");

      const styleElement = document.createElement("style");
      styleElement.id = "custom-fonts";
      styleElement.innerHTML = fontFaceStyles;

      const existingStyle = document.getElementById("custom-fonts");
      if (existingStyle) {
        existingStyle.remove();
      }

      document.head.appendChild(styleElement);
    } catch (loadError) {
      console.error("Failed to load fonts:", loadError);
    }
  }, [apiUrl]);

  const fetchAiModels = useCallback(
    async (
      provider: AiProvider,
      options?: { showStatus?: boolean; skipOllamaAutoPrompt?: boolean },
    ): Promise<boolean> => {
      const showStatus = options?.showStatus ?? true;
      const skipOllamaAutoPrompt = options?.skipOllamaAutoPrompt ?? false;
      if (!session?.user?.id) {
        return false;
      }

      if (showStatus) {
        setAiModelStatus(null);
      }
      setAiModelError(null);
      setIsLoadingAiModels(true);
      latestAiModelsRequestRef.current += 1;
      const requestId = latestAiModelsRequestRef.current;

      try {
        const params = new URLSearchParams();
        if (provider === "zai") {
          params.set("routing_mode", zaiRoutingMode);
        }
        if (provider === "ollama") {
          if (selectedOllamaProfile.trim()) {
            params.set("profile", selectedOllamaProfile.trim());
          } else if (ollamaServerUrl.trim()) {
            params.set("server_url", ollamaServerUrl.trim());
          }
          params.set("timeout_seconds", String(ollamaRequestControls.timeout_seconds));
          params.set("max_retries", String(ollamaRequestControls.max_retries));
          params.set("retry_backoff_ms", String(ollamaRequestControls.retry_backoff_ms));
        }
        const modelsUrl = `${apiUrl}/tasks/ai-settings/${provider}/models${params.toString() ? `?${params.toString()}` : ""}`;
        const response = await fetch(modelsUrl, {
          headers: {
            user_id: session.user.id,
          },
        });

        const responseData = await response
          .json()
          .catch(() => ({} as { detail?: string; models?: unknown }));
        if (!response.ok) {
          throw new Error(responseData?.detail || `Failed to load ${provider} models`);
        }

        const rawModels = Array.isArray(responseData.models)
          ? responseData.models.filter((value: unknown): value is string => typeof value === "string")
          : [];
        let models: string[] = Array.from(
          new Set(rawModels.map((value: string) => value.trim()).filter((value: string) => value.length > 0)),
        );
        if (models.length === 0 && provider !== "ollama") {
          throw new Error(`No models were returned for ${provider}`);
        }

        if (
          provider === "ollama" &&
          !skipOllamaAutoPrompt &&
          activeAiProviderRef.current === "ollama" &&
          !models.includes(DEFAULT_AI_MODELS.ollama)
        ) {
          const promptKey = `${selectedOllamaProfile.trim()}|${ollamaServerUrl.trim() || "default"}`;
          if (ollamaAutoEnsurePromptedRef.current !== promptKey && !ollamaAutoEnsureInFlightRef.current) {
            ollamaAutoEnsurePromptedRef.current = promptKey;
            const shouldInstall = window.confirm(
              `Ollama model ${DEFAULT_AI_MODELS.ollama} is not available on this server. Download it now?`,
            );
            if (shouldInstall) {
              ollamaAutoEnsureInFlightRef.current = true;
              setAiModelStatus(`Installing ${DEFAULT_AI_MODELS.ollama} on Ollama...`);
              setAiModelError(null);
              try {
                const ensureResponse = await fetch(`${apiUrl}/tasks/ai-settings/ollama/ensure-recommended-model`, {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/json",
                    user_id: session.user.id,
                  },
                  body: JSON.stringify({
                    confirm: true,
                    profile: selectedOllamaProfile || undefined,
                    base_url: selectedOllamaProfile ? undefined : ollamaServerUrl.trim() || undefined,
                    auth_mode: ollamaAuthToken.trim() ? ollamaAuthMode : undefined,
                    auth_header_name:
                      ollamaAuthToken.trim() && ollamaAuthMode === "custom_header"
                        ? ollamaAuthHeaderName.trim()
                        : undefined,
                    auth_token: ollamaAuthToken.trim() || undefined,
                    timeout_seconds: ollamaRequestControls.timeout_seconds,
                    max_retries: ollamaRequestControls.max_retries,
                    retry_backoff_ms: ollamaRequestControls.retry_backoff_ms,
                  }),
                });
                const ensureData = await ensureResponse
                  .json()
                  .catch(() => ({} as { detail?: string; models?: unknown; pulled?: boolean; already_available?: boolean }));
                if (!ensureResponse.ok) {
                  throw new Error(ensureData?.detail || `Failed to install ${DEFAULT_AI_MODELS.ollama}`);
                }
                const ensuredModels = Array.isArray(ensureData.models)
                  ? ensureData.models.filter((value: unknown): value is string => typeof value === "string")
                  : [];
                const normalizedEnsuredModels: string[] = Array.from(
                  new Set<string>(
                    ensuredModels
                      .map((value: string) => value.trim())
                      .filter((value: string) => value.length > 0),
                  ),
                );
                if (normalizedEnsuredModels.length > 0) {
                  models = normalizedEnsuredModels;
                }
                if (!models.includes(DEFAULT_AI_MODELS.ollama)) {
                  throw new Error(`${DEFAULT_AI_MODELS.ollama} is still unavailable after pull.`);
                }
                setAiModelStatus(
                  ensureData.pulled
                    ? `Installed ${DEFAULT_AI_MODELS.ollama}.`
                    : `${DEFAULT_AI_MODELS.ollama} is already available.`,
                );
              } catch (ensureError) {
                const message =
                  ensureError instanceof Error ? ensureError.message : `Failed to install ${DEFAULT_AI_MODELS.ollama}`;
                setAiModelError(message);
              } finally {
                ollamaAutoEnsureInFlightRef.current = false;
              }
            } else {
              setAiModelStatus(
                `${DEFAULT_AI_MODELS.ollama} is not installed. You can use another model and run viability tests.`,
              );
            }
          }
        }
        if (models.length === 0) {
          throw new Error(`No models were returned for ${provider}`);
        }

        setAiModelOptions((prev) => ({ ...prev, [provider]: models }));
        setHasLoadedAiModels((prev) => ({ ...prev, [provider]: true }));

        if (activeAiProviderRef.current === provider) {
          setPreferencesDraft((prev) => {
            if (prev.aiProvider !== provider) {
              return prev;
            }
            const trimmed = prev.aiModel.trim();
            if (trimmed && models.includes(trimmed)) {
              return prev;
            }
            if (models.includes(DEFAULT_AI_MODELS[provider])) {
              return { ...prev, aiModel: DEFAULT_AI_MODELS[provider] };
            }
            return { ...prev, aiModel: models[0] ?? DEFAULT_AI_MODELS[provider] };
          });

          if (showStatus) {
            setAiModelStatus(`Loaded ${models.length} models from ${provider}.`);
          }
        }
        return true;
      } catch (loadError) {
        const message = loadError instanceof Error ? loadError.message : `Failed to load ${provider} models`;
        setAiModelOptions((prev) => ({ ...prev, [provider]: FALLBACK_AI_MODEL_OPTIONS[provider] }));
        setHasLoadedAiModels((prev) => ({ ...prev, [provider]: false }));
        if (activeAiProviderRef.current === provider) {
          setAiModelError(message);
        }
        return false;
      } finally {
        if (latestAiModelsRequestRef.current === requestId) {
          setIsLoadingAiModels(false);
        }
      }
    },
    [
      apiUrl,
      ollamaAuthHeaderName,
      ollamaAuthMode,
      ollamaAuthToken,
      ollamaRequestControls.max_retries,
      ollamaRequestControls.retry_backoff_ms,
      ollamaRequestControls.timeout_seconds,
      ollamaServerUrl,
      selectedOllamaProfile,
      session?.user?.id,
      zaiRoutingMode,
    ],
  );

  const refreshAiSettings = useCallback(async (): Promise<void> => {
    if (!session?.user?.id) {
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/tasks/ai-settings`, {
        headers: {
          user_id: session.user.id,
        },
      });
      if (!response.ok) {
        return;
      }

      const data = await response.json();
      const parsedOllamaProfiles: OllamaProfileSummary[] = Array.isArray(data.ollama_profiles)
        ? data.ollama_profiles
            .filter((value: unknown) => typeof value === "object" && value !== null)
            .map((value: Record<string, unknown>) => ({
              profile_name: String(value.profile_name || "").trim(),
              base_url: String(value.base_url || "").trim(),
              auth_mode:
                value.auth_mode === "bearer" || value.auth_mode === "custom_header" || value.auth_mode === "none"
                  ? value.auth_mode
                  : "none",
              auth_header_name:
                typeof value.auth_header_name === "string" && value.auth_header_name.trim().length > 0
                  ? value.auth_header_name.trim()
                  : null,
              enabled: value.enabled !== false,
              is_default: value.is_default === true,
              has_auth_secret: value.has_auth_secret === true,
            }))
            .filter((value: OllamaProfileSummary) => value.profile_name.length > 0)
        : [];
      const defaultProfileFromApi =
        typeof data.default_ollama_profile === "string" && data.default_ollama_profile.trim().length > 0
          ? data.default_ollama_profile.trim()
          : parsedOllamaProfiles.find((profile) => profile.is_default)?.profile_name || "";
      const requestControlsFromApi =
        typeof data.ollama_request_controls === "object" && data.ollama_request_controls !== null
          ? data.ollama_request_controls
          : {};
      setHasSavedAiKeys({
        openai: Boolean(data.has_openai_key),
        google: Boolean(data.has_google_key),
        anthropic: Boolean(data.has_anthropic_key),
        zai: Boolean(data.has_zai_key),
        ollama: Boolean(data.has_ollama_server) || parsedOllamaProfiles.length > 0,
      });
      setHasSavedOllamaServer(Boolean(data.has_ollama_server) || parsedOllamaProfiles.length > 0);
      setOllamaProfiles(parsedOllamaProfiles);
      setHasSavedZaiProfileKeys({
        subscription: Boolean(data.has_zai_subscription_key),
        metered: Boolean(data.has_zai_metered_key),
      });
      if (typeof data.zai_routing_mode === "string" && isZaiRoutingMode(data.zai_routing_mode)) {
        setZaiRoutingMode(data.zai_routing_mode);
      }
      setHasEnvAiFallback({
        openai: Boolean(data.has_env_openai),
        google: Boolean(data.has_env_google),
        anthropic: Boolean(data.has_env_anthropic),
        zai: Boolean(data.has_env_zai),
        ollama: Boolean(data.has_env_ollama),
      });
      setHasEnvOllamaServer(Boolean(data.has_env_ollama));
      setOllamaRequestControls({
        timeout_seconds:
          typeof requestControlsFromApi.timeout_seconds === "number" && Number.isFinite(requestControlsFromApi.timeout_seconds)
            ? Math.max(1, Math.min(600, Math.round(requestControlsFromApi.timeout_seconds)))
            : DEFAULT_OLLAMA_REQUEST_CONTROLS.timeout_seconds,
        max_retries:
          typeof requestControlsFromApi.max_retries === "number" && Number.isFinite(requestControlsFromApi.max_retries)
            ? Math.max(0, Math.min(10, Math.round(requestControlsFromApi.max_retries)))
            : DEFAULT_OLLAMA_REQUEST_CONTROLS.max_retries,
        retry_backoff_ms:
          typeof requestControlsFromApi.retry_backoff_ms === "number" && Number.isFinite(requestControlsFromApi.retry_backoff_ms)
            ? Math.max(0, Math.min(30000, Math.round(requestControlsFromApi.retry_backoff_ms)))
            : DEFAULT_OLLAMA_REQUEST_CONTROLS.retry_backoff_ms,
      });
      setSelectedOllamaProfile((previous) => {
        if (previous && parsedOllamaProfiles.some((profile) => profile.profile_name === previous)) {
          return previous;
        }
        if (defaultProfileFromApi && parsedOllamaProfiles.some((profile) => profile.profile_name === defaultProfileFromApi)) {
          return defaultProfileFromApi;
        }
        return parsedOllamaProfiles[0]?.profile_name || "";
      });
      if (typeof data.ollama_server_url === "string" && data.ollama_server_url.trim().length > 0) {
        setOllamaServerUrl(data.ollama_server_url.trim());
      }
    } catch (loadError) {
      console.error("Failed to load AI settings:", loadError);
    }
  }, [apiUrl, session?.user?.id]);

  const savePreferences = useCallback(
    async (options?: SavePreferencesOptions): Promise<boolean> => {
      if (!session?.user?.id) {
        return false;
      }
      if (!isDirty) {
        return true;
      }

      setIsSavingPreferences(true);
      setSaveError(null);

      try {
        const resolvedAiModel = preferencesDraft.aiModel.trim() || DEFAULT_AI_MODELS[preferencesDraft.aiProvider];
        const payload: UserPreferences = {
          ...preferencesDraft,
          reviewBeforeRenderEnabled: true,
          aiModel: resolvedAiModel,
        };

        const response = await fetch("/api/preferences", {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          keepalive: options?.keepalive,
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({} as { error?: string }));
          throw new Error(errorData.error || "Failed to save preferences");
        }

        setPreferencesDraft(payload);
        setLastSavedSnapshot(payload);
        setSaveError(null);
        return true;
      } catch (savePreferencesError) {
        console.error("Error saving preferences:", savePreferencesError);
        setSaveError(savePreferencesError instanceof Error ? savePreferencesError.message : "Failed to save preferences");
        return false;
      } finally {
        setIsSavingPreferences(false);
      }
    },
    [isDirty, preferencesDraft, session?.user?.id],
  );

  const updateSectionQueryParam = useCallback(
    (section: SettingsSection) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set("section", section);
      router.replace(`/settings?${params.toString()}`);
    },
    [router, searchParams],
  );

  const handleSectionChange = useCallback(
    (section: SettingsSection) => {
      if (section === activeSection || isSavingPreferences) {
        return;
      }

      // Section changes should show persisted values, not unsaved draft edits.
      if (isDirty) {
        setPreferencesDraft({ ...lastSavedSnapshot });
        setSaveError(null);
      }

      updateSectionQueryParam(section);
    },
    [activeSection, isDirty, isSavingPreferences, lastSavedSnapshot, updateSectionQueryParam],
  );

  const saveAssemblyKey = useCallback(
    async (key: string): Promise<boolean> => {
      const trimmed = key.trim();
      if (!trimmed) {
        setAssemblyKeyError("AssemblyAI key cannot be empty.");
        return false;
      }

      setIsSavingAssemblyKey(true);
      setAssemblyKeyError(null);
      setAssemblyKeyStatus(null);

      try {
        const response = await fetch(`${apiUrl}/tasks/transcription-settings/assembly-key`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session?.user?.id || "",
          },
          body: JSON.stringify({ assembly_api_key: trimmed }),
        });

        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || "Failed to save AssemblyAI key");
        }

        setHasSavedAssemblyKey(true);
        setAssemblyApiKey("");
        setAssemblyKeyStatus("AssemblyAI key saved.");
        return true;
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : "Failed to save AssemblyAI key";
        setAssemblyKeyError(message);
        return false;
      } finally {
        setIsSavingAssemblyKey(false);
      }
    },
    [apiUrl, session?.user?.id],
  );

  const deleteAssemblyKey = useCallback(async (): Promise<void> => {
    setIsSavingAssemblyKey(true);
    setAssemblyKeyError(null);
    setAssemblyKeyStatus(null);

    try {
      const response = await fetch(`${apiUrl}/tasks/transcription-settings/assembly-key`, {
        method: "DELETE",
        headers: {
          user_id: session?.user?.id || "",
        },
      });

      const responseData = await response.json().catch(() => ({} as { detail?: string }));
      if (!response.ok) {
        throw new Error(responseData?.detail || "Failed to remove AssemblyAI key");
      }

      setHasSavedAssemblyKey(false);
      setAssemblyApiKey("");
      setAssemblyKeyStatus("AssemblyAI key removed.");
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : "Failed to remove AssemblyAI key";
      setAssemblyKeyError(message);
    } finally {
      setIsSavingAssemblyKey(false);
    }
  }, [apiUrl, session?.user?.id]);

  const saveAiProviderKey = useCallback(
    async (provider: AiProvider, key: string): Promise<boolean> => {
      const trimmed = key.trim();
      if (!trimmed) {
        setAiKeyError(`${provider} key cannot be empty.`);
        return false;
      }

      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);

      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/${provider}/key`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session?.user?.id || "",
          },
          body: JSON.stringify({ api_key: trimmed }),
        });

        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || `Failed to save ${provider} key`);
        }

        setHasSavedAiKeys((prev) => ({ ...prev, [provider]: true }));
        setAiApiKeys((prev) => ({ ...prev, [provider]: "" }));
        setAiKeyStatus(`${provider} key saved.`);
        void refreshAiSettings();
        void fetchAiModels(provider);
        return true;
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : `Failed to save ${provider} key`;
        setAiKeyError(message);
        return false;
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [apiUrl, fetchAiModels, refreshAiSettings, session?.user?.id],
  );

  const saveOllamaProfile = useCallback(
    async (profileName: string, options?: { setAsDefault?: boolean; clearAuthToken?: boolean }): Promise<boolean> => {
      const normalizedProfile = profileName.trim().toLowerCase();
      const trimmedUrl = ollamaServerUrl.trim();
      if (!normalizedProfile) {
        setAiKeyError("Ollama profile name is required.");
        return false;
      }
      if (!trimmedUrl) {
        setAiKeyError("Ollama server URL cannot be empty.");
        return false;
      }

      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);

      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/ollama/profiles/${encodeURIComponent(normalizedProfile)}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session?.user?.id || "",
          },
          body: JSON.stringify({
            base_url: trimmedUrl,
            auth_mode: ollamaAuthMode,
            auth_header_name: ollamaAuthMode === "custom_header" ? ollamaAuthHeaderName.trim() : null,
            auth_token: ollamaAuthToken.trim() || undefined,
            clear_auth_token: Boolean(options?.clearAuthToken),
            enabled: true,
            set_as_default: Boolean(options?.setAsDefault),
          }),
        });

        const responseData = await response
          .json()
          .catch(() => ({} as { detail?: string; profile?: { base_url?: string } }));
        if (!response.ok) {
          throw new Error(responseData?.detail || "Failed to save Ollama profile");
        }

        const normalizedServerUrl =
          typeof responseData.profile?.base_url === "string" && responseData.profile.base_url.trim().length > 0
            ? responseData.profile.base_url.trim()
            : trimmedUrl;
        setOllamaServerUrl(normalizedServerUrl);
        setSelectedOllamaProfile(normalizedProfile);
        setOllamaAuthToken("");
        setAiKeyStatus(`Ollama profile saved: ${normalizedProfile}.`);
        await refreshAiSettings();
        if (preferencesDraft.aiProvider === "ollama") {
          void fetchAiModels("ollama");
        }
        return true;
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : "Failed to save Ollama profile";
        setAiKeyError(message);
        return false;
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [
      apiUrl,
      fetchAiModels,
      ollamaAuthHeaderName,
      ollamaAuthMode,
      ollamaAuthToken,
      ollamaServerUrl,
      preferencesDraft.aiProvider,
      refreshAiSettings,
      session?.user?.id,
    ],
  );

  const createOllamaProfile = useCallback(async (): Promise<void> => {
    const created = await saveOllamaProfile(newOllamaProfileName, { setAsDefault: false });
    if (created) {
      setNewOllamaProfileName("");
    }
  }, [newOllamaProfileName, saveOllamaProfile]);

  const deleteOllamaProfile = useCallback(async (): Promise<void> => {
    if (!selectedOllamaProfile) {
      setAiKeyError("Select an Ollama profile to delete.");
      return;
    }
    setIsSavingAiKey(true);
    setAiKeyError(null);
    setAiKeyStatus(null);
    try {
      const response = await fetch(
        `${apiUrl}/tasks/ai-settings/ollama/profiles/${encodeURIComponent(selectedOllamaProfile)}`,
        {
          method: "DELETE",
          headers: {
            user_id: session?.user?.id || "",
          },
        },
      );
      const responseData = await response.json().catch(() => ({} as { detail?: string }));
      if (!response.ok) {
        throw new Error(responseData?.detail || "Failed to delete Ollama profile");
      }
      setAiKeyStatus(`Ollama profile deleted: ${selectedOllamaProfile}.`);
      await refreshAiSettings();
      if (preferencesDraft.aiProvider === "ollama") {
        void fetchAiModels("ollama");
      }
    } catch (deleteError) {
      const message = deleteError instanceof Error ? deleteError.message : "Failed to delete Ollama profile";
      setAiKeyError(message);
    } finally {
      setIsSavingAiKey(false);
    }
  }, [apiUrl, fetchAiModels, preferencesDraft.aiProvider, refreshAiSettings, selectedOllamaProfile, session?.user?.id]);

  const setDefaultOllamaProfile = useCallback(async (): Promise<void> => {
    if (!selectedOllamaProfile) {
      setAiKeyError("Select an Ollama profile to set as default.");
      return;
    }
    setIsSavingAiKey(true);
    setAiKeyError(null);
    setAiKeyStatus(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/ai-settings/ollama/default-profile`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          user_id: session?.user?.id || "",
        },
        body: JSON.stringify({ profile: selectedOllamaProfile }),
      });
      const responseData = await response.json().catch(() => ({} as { detail?: string }));
      if (!response.ok) {
        throw new Error(responseData?.detail || "Failed to set default Ollama profile");
      }
      setAiKeyStatus(`Default Ollama profile set: ${selectedOllamaProfile}.`);
      await refreshAiSettings();
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "Failed to set default Ollama profile";
      setAiKeyError(message);
    } finally {
      setIsSavingAiKey(false);
    }
  }, [apiUrl, refreshAiSettings, selectedOllamaProfile, session?.user?.id]);

  const saveOllamaRequestControls = useCallback(async (): Promise<void> => {
    setIsSavingAiKey(true);
    setAiKeyError(null);
    setAiKeyStatus(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/ai-settings/ollama/request-controls`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          user_id: session?.user?.id || "",
        },
        body: JSON.stringify({
          timeout_seconds: ollamaRequestControls.timeout_seconds,
          max_retries: ollamaRequestControls.max_retries,
          retry_backoff_ms: ollamaRequestControls.retry_backoff_ms,
        }),
      });
      const responseData = await response.json().catch(() => ({} as { detail?: string }));
      if (!response.ok) {
        throw new Error(responseData?.detail || "Failed to save Ollama request controls");
      }
      setAiKeyStatus("Ollama request controls saved.");
      await refreshAiSettings();
    } catch (saveError) {
      const message = saveError instanceof Error ? saveError.message : "Failed to save Ollama request controls";
      setAiKeyError(message);
    } finally {
      setIsSavingAiKey(false);
    }
  }, [apiUrl, ollamaRequestControls.max_retries, ollamaRequestControls.retry_backoff_ms, ollamaRequestControls.timeout_seconds, refreshAiSettings, session?.user?.id]);

  const testOllamaConnection = useCallback(async (): Promise<void> => {
    setIsTestingOllamaConnection(true);
    setOllamaConnectionError(null);
    setOllamaConnectionStatus(null);
    try {
      const response = await fetch(`${apiUrl}/tasks/ai-settings/ollama/test-connection`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          user_id: session?.user?.id || "",
        },
        body: JSON.stringify({
          profile: selectedOllamaProfile || undefined,
          base_url: selectedOllamaProfile ? undefined : ollamaServerUrl.trim() || undefined,
          auth_mode: ollamaAuthToken.trim() ? ollamaAuthMode : undefined,
          auth_header_name:
            ollamaAuthToken.trim() && ollamaAuthMode === "custom_header"
              ? ollamaAuthHeaderName.trim()
              : undefined,
          auth_token: ollamaAuthToken.trim() || undefined,
          timeout_seconds: ollamaRequestControls.timeout_seconds,
          max_retries: ollamaRequestControls.max_retries,
          retry_backoff_ms: ollamaRequestControls.retry_backoff_ms,
        }),
      });
      const responseData = await response
        .json()
        .catch(() => ({} as { detail?: string; connected?: boolean; server_url?: string; model_count?: number; version?: string; failure_reason?: string }));
      if (!response.ok) {
        throw new Error(responseData?.detail || "Failed to test Ollama connection");
      }
      if (responseData.connected) {
        const versionSuffix =
          typeof responseData.version === "string" && responseData.version.trim().length > 0
            ? ` (version ${responseData.version.trim()})`
            : "";
        setOllamaConnectionStatus(
          `Connected to ${String(responseData.server_url || ollamaServerUrl)} with ${Number(responseData.model_count || 0)} models${versionSuffix}.`,
        );
      } else {
        setOllamaConnectionError(String(responseData.failure_reason || "Connection test failed"));
      }
    } catch (testError) {
      const message = testError instanceof Error ? testError.message : "Failed to test Ollama connection";
      setOllamaConnectionError(message);
    } finally {
      setIsTestingOllamaConnection(false);
    }
  }, [
    apiUrl,
    ollamaAuthHeaderName,
    ollamaAuthMode,
    ollamaAuthToken,
    ollamaRequestControls.max_retries,
    ollamaRequestControls.retry_backoff_ms,
    ollamaRequestControls.timeout_seconds,
    ollamaServerUrl,
    selectedOllamaProfile,
    session?.user?.id,
  ]);

  const saveZaiProfileKey = useCallback(
    async (profile: "subscription" | "metered", key: string): Promise<boolean> => {
      const trimmed = key.trim();
      if (!trimmed) {
        setAiKeyError(`z.ai ${profile} key cannot be empty.`);
        return false;
      }

      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);

      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/zai/profiles/${profile}/key`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session?.user?.id || "",
          },
          body: JSON.stringify({ api_key: trimmed }),
        });
        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || `Failed to save z.ai ${profile} key`);
        }

        setHasSavedZaiProfileKeys((prev) => ({ ...prev, [profile]: true }));
        setHasSavedAiKeys((prev) => ({ ...prev, zai: true }));
        setZaiProfileApiKeys((prev) => ({ ...prev, [profile]: "" }));
        setAiKeyStatus(`z.ai ${profile} key saved.`);
        void refreshAiSettings();
        void fetchAiModels("zai");
        return true;
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : `Failed to save z.ai ${profile} key`;
        setAiKeyError(message);
        return false;
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [apiUrl, fetchAiModels, refreshAiSettings, session?.user?.id],
  );

  const deleteZaiProfileKey = useCallback(
    async (profile: "subscription" | "metered"): Promise<void> => {
      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);
      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/zai/profiles/${profile}/key`, {
          method: "DELETE",
          headers: {
            user_id: session?.user?.id || "",
          },
        });
        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || `Failed to remove z.ai ${profile} key`);
        }

        setHasSavedZaiProfileKeys((prev) => ({ ...prev, [profile]: false }));
        setZaiProfileApiKeys((prev) => ({ ...prev, [profile]: "" }));
        setAiKeyStatus(`z.ai ${profile} key removed.`);
        void refreshAiSettings();
      } catch (deleteError) {
        const message = deleteError instanceof Error ? deleteError.message : `Failed to remove z.ai ${profile} key`;
        setAiKeyError(message);
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [apiUrl, refreshAiSettings, session?.user?.id],
  );

  const saveZaiRoutingMode = useCallback(
    async (routingMode: ZaiRoutingMode): Promise<boolean> => {
      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);
      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/zai/routing-mode`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            user_id: session?.user?.id || "",
          },
          body: JSON.stringify({ routing_mode: routingMode }),
        });
        const responseData = await response.json().catch(() => ({} as { detail?: string; routing_mode?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || "Failed to save z.ai routing mode");
        }
        const returnedMode = typeof responseData.routing_mode === "string" ? responseData.routing_mode : routingMode;
        if (isZaiRoutingMode(returnedMode)) {
          setZaiRoutingMode(returnedMode);
        } else {
          setZaiRoutingMode(routingMode);
        }
        setAiKeyStatus(`z.ai routing mode saved: ${routingMode}.`);
        void refreshAiSettings();
        if (preferencesDraft.aiProvider === "zai") {
          void fetchAiModels("zai");
        }
        return true;
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : "Failed to save z.ai routing mode";
        setAiKeyError(message);
        return false;
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [apiUrl, fetchAiModels, preferencesDraft.aiProvider, refreshAiSettings, session?.user?.id],
  );

  const deleteAiProviderKey = useCallback(
    async (provider: AiProvider): Promise<void> => {
      setIsSavingAiKey(true);
      setAiKeyError(null);
      setAiKeyStatus(null);

      try {
        const response = await fetch(`${apiUrl}/tasks/ai-settings/${provider}/key`, {
          method: "DELETE",
          headers: {
            user_id: session?.user?.id || "",
          },
        });

        const responseData = await response.json().catch(() => ({} as { detail?: string }));
        if (!response.ok) {
          throw new Error(responseData?.detail || `Failed to remove ${provider} key`);
        }

        setHasSavedAiKeys((prev) => ({ ...prev, [provider]: false }));
        setAiApiKeys((prev) => ({ ...prev, [provider]: "" }));
        setAiKeyStatus(`${provider} key removed.`);
        void refreshAiSettings();

        if (!hasEnvAiFallback[provider]) {
          setAiModelOptions((prev) => ({ ...prev, [provider]: FALLBACK_AI_MODEL_OPTIONS[provider] }));
          setHasLoadedAiModels((prev) => ({ ...prev, [provider]: false }));
          if (preferencesDraft.aiProvider === provider) {
            setAiModelStatus(null);
            setAiModelError(null);
          }
        }
      } catch (deleteError) {
        const message = deleteError instanceof Error ? deleteError.message : `Failed to remove ${provider} key`;
        setAiKeyError(message);
      } finally {
        setIsSavingAiKey(false);
      }
    },
    [apiUrl, hasEnvAiFallback, preferencesDraft.aiProvider, refreshAiSettings, session?.user?.id],
  );

  const handleFontUpload = useCallback(
    async (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (!file) {
        return;
      }

      setFontUploadError(null);
      setFontUploadMessage(null);

      if (!file.name.toLowerCase().endsWith(".ttf")) {
        setFontUploadError("Only .ttf font files are supported.");
        event.target.value = "";
        return;
      }

      setIsUploadingFont(true);
      try {
        const formData = new FormData();
        formData.append("font", file);

        const response = await fetch(`${apiUrl}/fonts/upload`, {
          method: "POST",
          body: formData,
        });

        const responseData = await response
          .json()
          .catch(() => ({} as { detail?: string; message?: string; font?: { name?: string } }));

        if (!response.ok) {
          throw new Error(responseData?.detail || "Failed to upload font");
        }

        await loadFonts();

        if (typeof responseData?.font?.name === "string" && responseData.font.name.length > 0) {
          setPreferencesDraft((prev) => ({ ...prev, fontFamily: responseData.font?.name || prev.fontFamily }));
        }
        setFontUploadMessage(responseData?.message || "Font uploaded successfully.");
      } catch (uploadError) {
        setFontUploadError(uploadError instanceof Error ? uploadError.message : "Failed to upload font.");
      } finally {
        setIsUploadingFont(false);
        event.target.value = "";
      }
    },
    [apiUrl, loadFonts],
  );

  useEffect(() => {
    void loadFonts();
  }, [loadFonts]);

  useEffect(() => {
    if (!isPending && !session?.user?.id) {
      setIsFetching(false);
    }
  }, [isPending, session?.user?.id]);

  useEffect(() => {
    const sectionParam = searchParams.get("section");
    if (!isSettingsSection(sectionParam)) {
      updateSectionQueryParam("font");
    }
  }, [searchParams, updateSectionQueryParam]);

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }

    const loadPreferences = async () => {
      setIsFetching(true);
      try {
        const response = await fetch("/api/preferences");
        if (!response.ok) {
          return;
        }

        const data: Partial<UserPreferences> = await response.json();

        const resolvedAiProvider =
          typeof data.aiProvider === "string" && isAiProvider(data.aiProvider) ? data.aiProvider : "openai";

        const normalizedFontStyle = normalizeFontStyleOptions(data);
        const normalizedWhisperChunkDuration = normalizeWhisperChunkDurationSeconds(data.whisperChunkDurationSeconds);
        const normalizedWhisperChunkOverlap = normalizeWhisperChunkOverlapSeconds(
          data.whisperChunkOverlapSeconds,
          normalizedWhisperChunkDuration,
        );

        const nextPreferences: UserPreferences = {
          ...normalizedFontStyle,
          transitionsEnabled: Boolean(data.transitionsEnabled),
          reviewBeforeRenderEnabled: true,
          timelineEditorEnabled:
            typeof data.timelineEditorEnabled === "boolean"
              ? data.timelineEditorEnabled
              : DEFAULT_USER_PREFERENCES.timelineEditorEnabled,
          transcriptionProvider:
            typeof data.transcriptionProvider === "string" && isTranscriptionProvider(data.transcriptionProvider)
              ? data.transcriptionProvider
              : DEFAULT_USER_PREFERENCES.transcriptionProvider,
          whisperChunkingEnabled:
            typeof data.whisperChunkingEnabled === "boolean"
              ? data.whisperChunkingEnabled
              : DEFAULT_USER_PREFERENCES.whisperChunkingEnabled,
          whisperChunkDurationSeconds: normalizedWhisperChunkDuration,
          whisperChunkOverlapSeconds: normalizedWhisperChunkOverlap,
          taskTimeoutSeconds: normalizeTaskTimeoutSeconds(data.taskTimeoutSeconds),
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

        setPreferencesDraft(nextPreferences);
        setLastSavedSnapshot(nextPreferences);
        setSaveError(null);
      } catch (loadError) {
        console.error("Failed to load preferences:", loadError);
      } finally {
        setIsFetching(false);
      }
    };

    void loadPreferences();
  }, [session?.user?.id]);

  useEffect(() => {
    activeAiProviderRef.current = preferencesDraft.aiProvider;
  }, [preferencesDraft.aiProvider]);

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }

    const loadTranscriptionSettings = async () => {
      try {
        const response = await fetch(`${apiUrl}/tasks/transcription-settings`, {
          headers: {
            user_id: session.user.id,
          },
        });
        if (!response.ok) {
          return;
        }

        const data = await response.json();
        setHasSavedAssemblyKey(Boolean(data.has_assembly_key));
        setHasAssemblyEnvFallback(Boolean(data.has_env_fallback));
        setGpuWorkerEnabled(Boolean(data.gpu_worker_enabled));
        if (data.local_whisper_runtime && typeof data.local_whisper_runtime === "object") {
          setLocalWhisperRuntime(data.local_whisper_runtime as LocalWhisperRuntimeInfo);
        }
        if (Array.isArray(data.local_whisper_models)) {
          const parsedModels = data.local_whisper_models.filter((entry: unknown): entry is LocalWhisperModelOption => {
            if (!entry || typeof entry !== "object") {
              return false;
            }
            const candidate = entry as Partial<LocalWhisperModelOption>;
            return (
              typeof candidate.value === "string" &&
              typeof candidate.label === "string" &&
              typeof candidate.speed_hint === "string" &&
              typeof candidate.quality_hint === "string"
            );
          });
          setLocalWhisperModels(parsedModels.length > 0 ? parsedModels : FALLBACK_LOCAL_WHISPER_MODELS);
        }
        if (typeof data.assemblyai_max_duration_seconds === "number" && Number.isFinite(data.assemblyai_max_duration_seconds)) {
          setAssemblyMaxDurationSeconds(Math.max(1, Math.round(data.assemblyai_max_duration_seconds)));
        }
        if (
          typeof data.assemblyai_max_local_upload_size_bytes === "number" &&
          Number.isFinite(data.assemblyai_max_local_upload_size_bytes)
        ) {
          setAssemblyMaxLocalUploadSizeBytes(Math.max(1, Math.round(data.assemblyai_max_local_upload_size_bytes)));
        }
        const cap =
          typeof data.worker_timeout_cap_seconds === "number" && Number.isFinite(data.worker_timeout_cap_seconds)
            ? Math.max(300, Math.round(data.worker_timeout_cap_seconds))
            : MAX_TASK_TIMEOUT_SECONDS;
        setWorkerTimeoutCapSeconds(cap);
        setPreferencesDraft((prev) => ({
          ...prev,
          taskTimeoutSeconds: Math.min(prev.taskTimeoutSeconds, cap),
        }));
        setLastSavedSnapshot((prev) => ({
          ...prev,
          taskTimeoutSeconds: Math.min(prev.taskTimeoutSeconds, cap),
        }));
      } catch (loadError) {
        console.error("Failed to load transcription settings:", loadError);
      }
    };

    void loadTranscriptionSettings();
  }, [apiUrl, session?.user?.id]);

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }
    void refreshAiSettings();
  }, [refreshAiSettings, session?.user?.id]);

  useEffect(() => {
    if (selectedOllamaProfileMeta) {
      setOllamaServerUrl(selectedOllamaProfileMeta.base_url || ollamaServerUrl);
      setOllamaAuthMode(selectedOllamaProfileMeta.auth_mode);
      setOllamaAuthHeaderName(selectedOllamaProfileMeta.auth_header_name || "");
      setOllamaAuthToken("");
      return;
    }
    if (ollamaProfiles.length === 0) {
      setOllamaAuthMode("none");
      setOllamaAuthHeaderName("");
      setOllamaAuthToken("");
    }
  }, [ollamaProfiles.length, ollamaServerUrl, selectedOllamaProfileMeta]);

  useEffect(() => {
    if (!session?.user?.id) {
      return;
    }

    const provider = preferencesDraft.aiProvider;
    const hasProviderKey =
      provider === "zai"
        ? hasSavedAiKeys.zai || hasSavedZaiProfileKeys.subscription || hasSavedZaiProfileKeys.metered || hasEnvAiFallback.zai
        : provider === "ollama"
          ? Boolean(ollamaServerUrl.trim()) || hasEnvOllamaServer || ollamaProfiles.length > 0
        : hasSavedAiKeys[provider] || hasEnvAiFallback[provider];
    if (!hasProviderKey) {
      setAiModelOptions((prev) => ({ ...prev, [provider]: FALLBACK_AI_MODEL_OPTIONS[provider] }));
      setHasLoadedAiModels((prev) => ({ ...prev, [provider]: false }));
      setAiModelStatus(null);
      setAiModelError(null);
      return;
    }

    void fetchAiModels(provider, { showStatus: false });
  }, [
    fetchAiModels,
    hasEnvAiFallback,
    hasSavedAiKeys,
    hasSavedZaiProfileKeys.metered,
    hasSavedZaiProfileKeys.subscription,
    hasEnvOllamaServer,
    ollamaProfiles.length,
    ollamaServerUrl,
    preferencesDraft.aiProvider,
    selectedOllamaProfile,
    session?.user?.id,
    zaiRoutingMode,
  ]);

  useEffect(() => {
    if (!isDirty || isSavingPreferences) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
      void savePreferences({ keepalive: true });
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [isDirty, isSavingPreferences, savePreferences]);

  if (isPending || isFetching) {
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
          <div className="text-center">
            <h1 className="text-3xl font-bold text-black mb-4">Sign In Required</h1>
            <p className="text-gray-600 mb-8">You need to sign in to access your settings</p>
            <Link href="/sign-in">
              <Button size="lg">Sign In</Button>
            </Link>
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
            <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity cursor-pointer">
              <Image src="/brand/logo.png" alt="MrglSnips logo" width={96} height={96} className="h-24 w-24 object-contain" />
              <h1 className="text-xl font-bold text-black">MrglSnips</h1>
            </Link>

            <div className="flex items-center gap-3">
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
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 py-10">
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <Settings className="w-6 h-6 text-black" />
            <h2 className="text-2xl font-bold text-black">Settings</h2>
          </div>
          <p className="text-gray-600">
            Configure your default preferences for video clip generation and per-user API keys.
          </p>
        </div>

        <div className="md:hidden mb-4 space-y-2">
          <Label className="text-sm font-medium text-black">Section</Label>
          <Select
            value={activeSection}
            onValueChange={(value) => {
              if (isSettingsSection(value)) {
                void handleSectionChange(value);
              }
            }}
            disabled={isSavingPreferences}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select section" />
            </SelectTrigger>
            <SelectContent>
              {SETTINGS_SECTIONS.map((section) => (
                <SelectItem key={section} value={section}>
                  {SETTINGS_SECTION_META[section].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="grid md:grid-cols-[260px_1fr] gap-6">
          <SettingsSidebar
            sections={sectionNavItems}
            activeSection={activeSection}
            isSaving={isSavingPreferences}
            onSectionSelect={(section) => {
              void handleSectionChange(section);
            }}
          />

          <section className="rounded-lg border border-gray-200 bg-white p-4 sm:p-6">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-black">{SETTINGS_SECTION_META[activeSection].label}</p>
                <p className="text-xs text-gray-500">
                  {SETTINGS_SECTION_META[activeSection].description} Use Save to apply changes.
                </p>
              </div>
              <SettingsSaveStatus isDirty={isDirty} isSaving={isSavingPreferences} saveError={saveError} />
            </div>

            {saveError && (
              <Alert className="mb-4 border-red-200 bg-red-50">
                <AlertCircle className="h-4 w-4 text-red-500" />
                <AlertDescription className="text-sm text-red-700">{saveError}</AlertDescription>
              </Alert>
            )}

            {activeSection === "font" ? (
              <SettingsSectionFont
                isSaving={isSavingPreferences}
                availableFonts={availableFonts}
                fontFamily={preferencesDraft.fontFamily}
                fontSize={preferencesDraft.fontSize}
                fontColor={preferencesDraft.fontColor}
                highlightColor={preferencesDraft.highlightColor}
                fontWeight={preferencesDraft.fontWeight}
                lineHeight={preferencesDraft.lineHeight}
                letterSpacing={preferencesDraft.letterSpacing}
                textTransform={preferencesDraft.textTransform}
                textAlign={preferencesDraft.textAlign}
                strokeColor={preferencesDraft.strokeColor}
                strokeWidth={preferencesDraft.strokeWidth}
                strokeBlur={preferencesDraft.strokeBlur}
                shadowColor={preferencesDraft.shadowColor}
                shadowOpacity={preferencesDraft.shadowOpacity}
                shadowBlur={preferencesDraft.shadowBlur}
                shadowOffsetX={preferencesDraft.shadowOffsetX}
                shadowOffsetY={preferencesDraft.shadowOffsetY}
                isUploadingFont={isUploadingFont}
                fontUploadMessage={fontUploadMessage}
                fontUploadError={fontUploadError}
                onFontFamilyChange={(value) => {
                  setPreferencesDraft((prev) => ({ ...prev, fontFamily: value }));
                }}
                onFontSizeChange={(size) => {
                  setPreferencesDraft((prev) => ({ ...prev, fontSize: normalizeFontSize(size) }));
                }}
                onFontColorChange={(color) => {
                  setPreferencesDraft((prev) => ({ ...prev, fontColor: color }));
                }}
                onHighlightColorChange={(highlightColor) => {
                  setPreferencesDraft((prev) => ({ ...prev, highlightColor }));
                }}
                onFontWeightChange={(weight) => {
                  setPreferencesDraft((prev) => ({ ...prev, fontWeight: normalizeFontWeight(weight) }));
                }}
                onLineHeightChange={(lineHeight) => {
                  setPreferencesDraft((prev) => ({ ...prev, lineHeight: normalizeLineHeight(lineHeight) }));
                }}
                onLetterSpacingChange={(spacing) => {
                  setPreferencesDraft((prev) => ({ ...prev, letterSpacing: normalizeLetterSpacing(spacing) }));
                }}
                onTextTransformChange={(textTransform) => {
                  setPreferencesDraft((prev) => ({ ...prev, textTransform: textTransform as TextTransformOption }));
                }}
                onTextAlignChange={(textAlign) => {
                  setPreferencesDraft((prev) => ({ ...prev, textAlign: textAlign as TextAlignOption }));
                }}
                onStrokeColorChange={(strokeColor) => {
                  setPreferencesDraft((prev) => ({ ...prev, strokeColor }));
                }}
                onStrokeWidthChange={(strokeWidth) => {
                  setPreferencesDraft((prev) => ({ ...prev, strokeWidth: normalizeStrokeWidth(strokeWidth) }));
                }}
                onStrokeBlurChange={(strokeBlur) => {
                  setPreferencesDraft((prev) => ({ ...prev, strokeBlur: normalizeStrokeBlur(strokeBlur) }));
                }}
                onShadowColorChange={(shadowColor) => {
                  setPreferencesDraft((prev) => ({ ...prev, shadowColor }));
                }}
                onShadowOpacityChange={(shadowOpacity) => {
                  setPreferencesDraft((prev) => ({ ...prev, shadowOpacity: normalizeShadowOpacity(shadowOpacity) }));
                }}
                onShadowBlurChange={(shadowBlur) => {
                  setPreferencesDraft((prev) => ({ ...prev, shadowBlur: normalizeShadowBlur(shadowBlur) }));
                }}
                onShadowOffsetXChange={(shadowOffsetX) => {
                  setPreferencesDraft((prev) => ({ ...prev, shadowOffsetX: normalizeShadowOffset(shadowOffsetX) }));
                }}
                onShadowOffsetYChange={(shadowOffsetY) => {
                  setPreferencesDraft((prev) => ({ ...prev, shadowOffsetY: normalizeShadowOffset(shadowOffsetY) }));
                }}
                onFontUpload={handleFontUpload}
              />
            ) : activeSection === "video" ? (
              <SettingsSectionVideo
                isSaving={isSavingPreferences}
                transitionsEnabled={preferencesDraft.transitionsEnabled}
                timelineEditorEnabled={preferencesDraft.timelineEditorEnabled}
                onToggleTransitions={() => {
                  setPreferencesDraft((prev) => ({ ...prev, transitionsEnabled: !prev.transitionsEnabled }));
                }}
                onToggleTimelineEditor={() => {
                  setPreferencesDraft((prev) => ({ ...prev, timelineEditorEnabled: !prev.timelineEditorEnabled }));
                }}
              />
            ) : activeSection === "transcription" ? (
              <SettingsSectionTranscription
                isSaving={isSavingPreferences}
                transcriptionProvider={preferencesDraft.transcriptionProvider}
                whisperChunkingEnabled={preferencesDraft.whisperChunkingEnabled}
                whisperChunkDurationSeconds={preferencesDraft.whisperChunkDurationSeconds}
                whisperChunkOverlapSeconds={preferencesDraft.whisperChunkOverlapSeconds}
                taskTimeoutSeconds={preferencesDraft.taskTimeoutSeconds}
                taskTimeoutMaxSeconds={workerTimeoutCapSeconds}
                whisperModelSize={preferencesDraft.whisperModelSize}
                whisperDevice={preferencesDraft.whisperDevice}
                whisperGpuIndex={preferencesDraft.whisperGpuIndex}
                localWhisperModels={localWhisperModels}
                localWhisperRuntime={localWhisperRuntime}
                gpuWorkerEnabled={gpuWorkerEnabled}
                isSavingAssemblyKey={isSavingAssemblyKey}
                assemblyApiKey={assemblyApiKey}
                hasSavedAssemblyKey={hasSavedAssemblyKey}
                hasAssemblyEnvFallback={hasAssemblyEnvFallback}
                assemblyMaxDurationSeconds={assemblyMaxDurationSeconds}
                assemblyMaxLocalUploadSizeBytes={assemblyMaxLocalUploadSizeBytes}
                assemblyKeyStatus={assemblyKeyStatus}
                assemblyKeyError={assemblyKeyError}
                onTranscriptionProviderChange={(provider) => {
                  if (isTranscriptionProvider(provider)) {
                    setPreferencesDraft((prev) => ({ ...prev, transcriptionProvider: provider }));
                  }
                  setAssemblyKeyStatus(null);
                  setAssemblyKeyError(null);
                }}
                onWhisperChunkingEnabledChange={(enabled) => {
                  setPreferencesDraft((prev) => ({ ...prev, whisperChunkingEnabled: enabled }));
                }}
                onWhisperChunkDurationSecondsChange={(seconds) => {
                  setPreferencesDraft((prev) => {
                    const nextDuration = normalizeWhisperChunkDurationSeconds(seconds);
                    const nextOverlap = normalizeWhisperChunkOverlapSeconds(prev.whisperChunkOverlapSeconds, nextDuration);
                    return {
                      ...prev,
                      whisperChunkDurationSeconds: nextDuration,
                      whisperChunkOverlapSeconds: nextOverlap,
                    };
                  });
                }}
                onWhisperChunkOverlapSecondsChange={(seconds) => {
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    whisperChunkOverlapSeconds: normalizeWhisperChunkOverlapSeconds(
                      seconds,
                      prev.whisperChunkDurationSeconds,
                    ),
                  }));
                }}
                onTaskTimeoutSecondsChange={(seconds) => {
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    taskTimeoutSeconds: Math.min(workerTimeoutCapSeconds, normalizeTaskTimeoutSeconds(seconds)),
                  }));
                }}
                onWhisperPresetChange={(preset) => {
                  const resolvedPreset = resolveWhisperPresetValues(
                    preset as Exclude<WhisperPresetId, "custom">,
                    localWhisperRuntime,
                  );
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    ...resolvedPreset,
                  }));
                }}
                onWhisperModelSizeChange={(modelSize) => {
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    whisperModelSize: modelSize,
                  }));
                }}
                onWhisperDeviceChange={(device) => {
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    whisperDevice: device,
                    whisperGpuIndex: device === "cpu" ? null : prev.whisperGpuIndex,
                  }));
                }}
                onWhisperGpuIndexChange={(gpuIndex) => {
                  setPreferencesDraft((prev) => ({
                    ...prev,
                    whisperGpuIndex: gpuIndex,
                  }));
                }}
                onAssemblyApiKeyChange={setAssemblyApiKey}
                onSaveAssemblyKey={() => {
                  void saveAssemblyKey(assemblyApiKey);
                }}
                onDeleteAssemblyKey={() => {
                  void deleteAssemblyKey();
                }}
              />
            ) : (
              <SettingsSectionAi
                isSaving={isSavingPreferences}
                aiProvider={preferencesDraft.aiProvider}
                aiModel={preferencesDraft.aiModel}
                aiModelOptions={aiModelOptions[preferencesDraft.aiProvider]}
                hasLoadedAiModels={hasLoadedAiModels[preferencesDraft.aiProvider]}
                hasAiKeyForSelectedProvider={hasAiKeyForSelectedProvider}
                isLoadingAiModels={isLoadingAiModels}
                isSavingAiKey={isSavingAiKey}
                aiApiKey={aiApiKeys[preferencesDraft.aiProvider]}
                hasSavedAiKey={hasSavedAiKeys[preferencesDraft.aiProvider]}
                hasEnvAiFallback={hasEnvAiFallback[preferencesDraft.aiProvider]}
                ollamaServerUrl={ollamaServerUrl}
                hasSavedOllamaServer={hasSavedOllamaServer}
                hasEnvOllamaServer={hasEnvOllamaServer}
                ollamaProfiles={ollamaProfiles}
                selectedOllamaProfile={selectedOllamaProfile}
                newOllamaProfileName={newOllamaProfileName}
                ollamaAuthMode={ollamaAuthMode}
                ollamaAuthHeaderName={ollamaAuthHeaderName}
                ollamaAuthToken={ollamaAuthToken}
                ollamaTimeoutSeconds={ollamaRequestControls.timeout_seconds}
                ollamaMaxRetries={ollamaRequestControls.max_retries}
                ollamaRetryBackoffMs={ollamaRequestControls.retry_backoff_ms}
                isTestingOllamaConnection={isTestingOllamaConnection}
                ollamaConnectionStatus={ollamaConnectionStatus}
                ollamaConnectionError={ollamaConnectionError}
                aiKeyStatus={aiKeyStatus}
                aiKeyError={aiKeyError}
                aiModelStatus={aiModelStatus}
                aiModelError={aiModelError}
                selectedZaiKeyProfile={selectedZaiKeyProfile}
                zaiRoutingMode={zaiRoutingMode}
                zaiProfileApiKey={zaiProfileApiKeys[selectedZaiKeyProfile]}
                hasSavedZaiSubscriptionKey={hasSavedZaiProfileKeys.subscription}
                hasSavedZaiMeteredKey={hasSavedZaiProfileKeys.metered}
                onAiProviderChange={(provider) => {
                  if (!isAiProvider(provider)) {
                    return;
                  }
                  if (provider === "ollama") {
                    ollamaAutoEnsurePromptedRef.current = null;
                  }

                  setPreferencesDraft((prev) => {
                    const prevDefaultModel = DEFAULT_AI_MODELS[prev.aiProvider];
                    const trimmedModel = prev.aiModel.trim();
                    const nextModel =
                      !trimmedModel || trimmedModel === prevDefaultModel ? DEFAULT_AI_MODELS[provider] : prev.aiModel;

                    return {
                      ...prev,
                      aiProvider: provider,
                      aiModel: nextModel,
                    };
                  });

                  setAiKeyStatus(null);
                  setAiKeyError(null);
                  setAiModelStatus(null);
                  setAiModelError(null);
                }}
                onAiModelChange={(model) => {
                  setPreferencesDraft((prev) => ({ ...prev, aiModel: model }));
                }}
                onAiApiKeyChange={(value) => {
                  setAiApiKeys((prev) => ({ ...prev, [preferencesDraft.aiProvider]: value }));
                }}
                onSaveAiProviderKey={() => {
                  const provider = preferencesDraft.aiProvider;
                  void saveAiProviderKey(provider, aiApiKeys[provider]);
                }}
                onDeleteAiProviderKey={() => {
                  void deleteAiProviderKey(preferencesDraft.aiProvider);
                }}
                onOllamaServerUrlChange={setOllamaServerUrl}
                onSelectedOllamaProfileChange={setSelectedOllamaProfile}
                onNewOllamaProfileNameChange={setNewOllamaProfileName}
                onCreateOllamaProfile={() => {
                  void createOllamaProfile();
                }}
                onSaveOllamaProfile={() => {
                  const profileToSave = selectedOllamaProfile || newOllamaProfileName || "default";
                  void saveOllamaProfile(profileToSave);
                }}
                onDeleteOllamaProfile={() => {
                  void deleteOllamaProfile();
                }}
                onSetDefaultOllamaProfile={() => {
                  void setDefaultOllamaProfile();
                }}
                onOllamaAuthModeChange={setOllamaAuthMode}
                onOllamaAuthHeaderNameChange={setOllamaAuthHeaderName}
                onOllamaAuthTokenChange={setOllamaAuthToken}
                onOllamaTimeoutSecondsChange={(value) => {
                  setOllamaRequestControls((prev) => ({
                    ...prev,
                    timeout_seconds: Number.isFinite(value) ? Math.max(1, Math.min(600, Math.round(value))) : prev.timeout_seconds,
                  }));
                }}
                onOllamaMaxRetriesChange={(value) => {
                  setOllamaRequestControls((prev) => ({
                    ...prev,
                    max_retries: Number.isFinite(value) ? Math.max(0, Math.min(10, Math.round(value))) : prev.max_retries,
                  }));
                }}
                onOllamaRetryBackoffMsChange={(value) => {
                  setOllamaRequestControls((prev) => ({
                    ...prev,
                    retry_backoff_ms:
                      Number.isFinite(value) ? Math.max(0, Math.min(30000, Math.round(value))) : prev.retry_backoff_ms,
                  }));
                }}
                onSaveOllamaRequestControls={() => {
                  void saveOllamaRequestControls();
                }}
                onTestOllamaConnection={() => {
                  void testOllamaConnection();
                }}
                onRefreshAiModels={() => {
                  if (preferencesDraft.aiProvider === "ollama") {
                    ollamaAutoEnsurePromptedRef.current = null;
                  }
                  void fetchAiModels(preferencesDraft.aiProvider);
                }}
                onSelectedZaiKeyProfileChange={setSelectedZaiKeyProfile}
                onZaiRoutingModeChange={(mode) => {
                  if (!isZaiRoutingMode(mode)) {
                    return;
                  }
                  setZaiRoutingMode(mode);
                  void saveZaiRoutingMode(mode);
                }}
                onZaiProfileApiKeyChange={(value) => {
                  setZaiProfileApiKeys((prev) => ({ ...prev, [selectedZaiKeyProfile]: value }));
                }}
                onSaveZaiProfileKey={() => {
                  void saveZaiProfileKey(selectedZaiKeyProfile, zaiProfileApiKeys[selectedZaiKeyProfile]);
                }}
                onDeleteZaiProfileKey={() => {
                  void deleteZaiProfileKey(selectedZaiKeyProfile);
                }}
              />
            )}

            <div className="mt-6 flex justify-end">
              <Button
                type="button"
                variant={isDirty ? "default" : "outline"}
                className={
                  isDirty
                    ? "border-emerald-600 bg-emerald-600 text-white hover:bg-emerald-500"
                    : "border-gray-500/60 text-gray-200"
                }
                onClick={() => {
                  void savePreferences();
                }}
                disabled={isSavingPreferences || !isDirty}
              >
                {isSavingPreferences
                  ? "Saving..."
                  : activeSection === "font"
                    ? "Save Fonts"
                    : activeSection === "video"
                      ? "Save Video"
                      : activeSection === "transcription"
                        ? "Save Transcription"
                        : "Save AI"}
              </Button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function SettingsPageFallback() {
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

export default function SettingsPage() {
  return (
    <Suspense fallback={<SettingsPageFallback />}>
      <SettingsPageContent />
    </Suspense>
  );
}
