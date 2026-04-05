import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { AiProvider } from "../settings-section-types";
import { AI_PROVIDERS, DEFAULT_AI_MODELS } from "../settings-section-types";

interface SettingsSectionAiProps {
  isSaving: boolean;
  aiProvider: AiProvider;
  aiModel: string;
  aiModelOptions: string[];
  hasLoadedAiModels: boolean;
  hasAiConnectionForSelectedProvider: boolean;
  isLoadingAiModels: boolean;
  aiModelStatus: string | null;
  aiModelError: string | null;
  onAiProviderChange: (provider: AiProvider) => void;
  onAiModelChange: (model: string) => void;
  onRefreshAiModels: () => void;
}

export function SettingsSectionAi({
  isSaving,
  aiProvider,
  aiModel,
  aiModelOptions,
  hasLoadedAiModels,
  hasAiConnectionForSelectedProvider,
  isLoadingAiModels,
  aiModelStatus,
  aiModelError,
  onAiProviderChange,
  onAiModelChange,
  onRefreshAiModels,
}: SettingsSectionAiProps) {
  const [isModelMenuOpen, setIsModelMenuOpen] = useState(false);
  const [shouldFilterModelOptions, setShouldFilterModelOptions] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement | null>(null);
  const normalizedModelQuery = aiModel.trim().toLowerCase();

  const visibleAiModelOptions = useMemo(() => {
    if (!isModelMenuOpen) {
      return [];
    }
    if (!shouldFilterModelOptions || normalizedModelQuery.length === 0) {
      return aiModelOptions;
    }
    return aiModelOptions.filter((model) => model.toLowerCase().includes(normalizedModelQuery));
  }, [aiModelOptions, isModelMenuOpen, normalizedModelQuery, shouldFilterModelOptions]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!modelMenuRef.current) {
        return;
      }
      if (!modelMenuRef.current.contains(event.target as Node)) {
        setIsModelMenuOpen(false);
        setShouldFilterModelOptions(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const openModelMenu = () => {
    setIsModelMenuOpen(true);
    setShouldFilterModelOptions(false);
  };

  const toggleModelMenu = () => {
    setIsModelMenuOpen((prev) => !prev);
    setShouldFilterModelOptions(false);
  };

  const closeModelMenu = () => {
    setIsModelMenuOpen(false);
    setShouldFilterModelOptions(false);
  };

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Default clip-selection provider</p>
          <p className="text-xs text-gray-500">Choose which LLM analyzes transcripts when new tasks are created.</p>
        </div>

        <Select value={aiProvider} onValueChange={(value) => onAiProviderChange(value as AiProvider)} disabled={isSaving}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select provider" />
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
      </div>

      <div className="space-y-3 rounded-md border border-gray-200 bg-white p-4">
        <div>
          <p className="text-sm font-medium text-black">Default model</p>
          <p className="text-xs text-gray-500">
            Keep this close to your preferred daily model. Connections and API keys are managed in the Connections tab.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isSaving || isLoadingAiModels || !hasAiConnectionForSelectedProvider}
            onClick={onRefreshAiModels}
          >
            {isLoadingAiModels ? "Loading Models..." : "Refresh Models"}
          </Button>
          {!hasAiConnectionForSelectedProvider ? (
            <span className="text-xs text-gray-500">
              Configure this provider in Connections before loading models.
            </span>
          ) : null}
        </div>

        <div
          ref={modelMenuRef}
          className="relative"
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              closeModelMenu();
            }
          }}
        >
          <div className="flex items-center gap-2">
            <Input
              id="ai-provider-model"
              value={aiModel}
              onFocus={() => {
                if (!isSaving) {
                  openModelMenu();
                }
              }}
              onChange={(event) => {
                onAiModelChange(event.target.value ?? "");
                if (!isSaving) {
                  setIsModelMenuOpen(true);
                  setShouldFilterModelOptions(true);
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "ArrowDown" && !isModelMenuOpen) {
                  event.preventDefault();
                  openModelMenu();
                }
                if (event.key === "Escape" || event.key === "Tab") {
                  closeModelMenu();
                }
              }}
              placeholder={`Default: ${DEFAULT_AI_MODELS[aiProvider]}`}
              disabled={isSaving}
            />
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Show model options"
              disabled={isSaving}
              onClick={toggleModelMenu}
            >
              <ChevronDown className="h-4 w-4" />
            </Button>
          </div>

          {isModelMenuOpen ? (
            <div className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
              {visibleAiModelOptions.length > 0 ? (
                visibleAiModelOptions.map((model) => (
                  <button
                    key={model}
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm text-black hover:bg-gray-50"
                    onMouseDown={(event) => {
                      event.preventDefault();
                    }}
                    onClick={() => {
                      onAiModelChange(model);
                      closeModelMenu();
                    }}
                  >
                    {model}
                  </button>
                ))
              ) : (
                <p className="px-3 py-2 text-sm text-gray-500">No matching models.</p>
              )}
            </div>
          ) : null}
        </div>

        <p className="text-xs text-gray-500">
          Clear the field to revert to the provider default: {DEFAULT_AI_MODELS[aiProvider]}.
        </p>
        {hasLoadedAiModels ? (
          <p className="text-xs text-gray-500">Loaded {aiModelOptions.length} model options directly from {aiProvider}.</p>
        ) : null}
        {aiModelStatus ? <p className="text-xs text-green-600">{aiModelStatus}</p> : null}
        {aiModelError ? <p className="text-xs text-red-600">{aiModelError}</p> : null}
      </div>
    </div>
  );
}
