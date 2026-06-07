import type {
  DefaultFramingMode,
  FaceAnchorProfile,
  FaceDetectionMode,
  FallbackCropPosition,
  PersistedProcessingProfile,
  ProcessingProfile,
  WorkflowSource,
} from "@/app/settings/settings-section-types";

export interface ProcessingProfileControlledValues {
  reviewBeforeRenderEnabled: boolean;
  timelineEditorEnabled: boolean;
  transitionsEnabled: boolean;
  transcriptionProvider: "local" | "assemblyai";
  whisperModelSize: "tiny" | "base" | "small" | "medium" | "large" | "turbo";
  defaultFramingMode: DefaultFramingMode;
  faceDetectionMode: FaceDetectionMode;
  fallbackCropPosition: FallbackCropPosition;
  faceAnchorProfile: FaceAnchorProfile;
}

export interface ProcessingProfilePreset extends ProcessingProfileControlledValues {
  id: ProcessingProfile;
  label: string;
  description: string;
}

export interface SavedWorkflow extends ProcessingProfileControlledValues {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export type WorkflowSelection =
  | { kind: "built_in"; id: ProcessingProfile }
  | { kind: "saved"; id: string }
  | { kind: "custom" };

export const PROCESSING_PROFILE_PRESETS: Record<ProcessingProfile, ProcessingProfilePreset> = {
  fast_draft: {
    id: "fast_draft",
    label: "Fast draft",
    description: "Quick local passes with review enabled and lighter transcription defaults.",
    reviewBeforeRenderEnabled: true,
    timelineEditorEnabled: true,
    transitionsEnabled: false,
    transcriptionProvider: "local",
    whisperModelSize: "turbo",
    defaultFramingMode: "auto",
    faceDetectionMode: "balanced",
    fallbackCropPosition: "center",
    faceAnchorProfile: "auto",
  },
  balanced: {
    id: "balanced",
    label: "Balanced",
    description: "Recommended default for most tasks.",
    reviewBeforeRenderEnabled: true,
    timelineEditorEnabled: true,
    transitionsEnabled: false,
    transcriptionProvider: "local",
    whisperModelSize: "medium",
    defaultFramingMode: "auto",
    faceDetectionMode: "balanced",
    fallbackCropPosition: "center",
    faceAnchorProfile: "auto",
  },
  best_quality: {
    id: "best_quality",
    label: "Best quality",
    description: "Higher-quality transcription and more face-aware defaults.",
    reviewBeforeRenderEnabled: true,
    timelineEditorEnabled: true,
    transitionsEnabled: false,
    transcriptionProvider: "local",
    whisperModelSize: "large",
    defaultFramingMode: "prefer_face",
    faceDetectionMode: "more_faces",
    fallbackCropPosition: "center",
    faceAnchorProfile: "center_only",
  },
  stream_layout: {
    id: "stream_layout",
    label: "Stream layout",
    description: "Optimized for solo streams with off-center framing.",
    reviewBeforeRenderEnabled: true,
    timelineEditorEnabled: true,
    transitionsEnabled: false,
    transcriptionProvider: "local",
    whisperModelSize: "turbo",
    defaultFramingMode: "prefer_face",
    faceDetectionMode: "more_faces",
    fallbackCropPosition: "left_center",
    faceAnchorProfile: "left_or_center",
  },
};

const BUILT_IN_WORKFLOW_IDS = Object.keys(PROCESSING_PROFILE_PRESETS) as ProcessingProfile[];

export function getProcessingProfilePreset(profile: ProcessingProfile): ProcessingProfilePreset {
  return PROCESSING_PROFILE_PRESETS[profile] ?? PROCESSING_PROFILE_PRESETS.balanced;
}

export function getProcessingProfileControlledValues(
  profile: ProcessingProfile,
): ProcessingProfileControlledValues {
  const preset = getProcessingProfilePreset(profile);
  return {
    reviewBeforeRenderEnabled: preset.reviewBeforeRenderEnabled,
    timelineEditorEnabled: preset.timelineEditorEnabled,
    transitionsEnabled: preset.transitionsEnabled,
    transcriptionProvider: preset.transcriptionProvider,
    whisperModelSize: preset.whisperModelSize,
    defaultFramingMode: preset.defaultFramingMode,
    faceDetectionMode: preset.faceDetectionMode,
    fallbackCropPosition: preset.fallbackCropPosition,
    faceAnchorProfile: preset.faceAnchorProfile,
  };
}

export function getSavedWorkflowControlledValues(workflow: SavedWorkflow): ProcessingProfileControlledValues {
  return {
    reviewBeforeRenderEnabled: workflow.reviewBeforeRenderEnabled,
    timelineEditorEnabled: workflow.timelineEditorEnabled,
    transitionsEnabled: workflow.transitionsEnabled,
    transcriptionProvider: workflow.transcriptionProvider,
    whisperModelSize: workflow.whisperModelSize,
    defaultFramingMode: workflow.defaultFramingMode,
    faceDetectionMode: workflow.faceDetectionMode,
    fallbackCropPosition: workflow.fallbackCropPosition,
    faceAnchorProfile: workflow.faceAnchorProfile,
  };
}

export function workflowMatchesValues(
  values: ProcessingProfileControlledValues,
  candidate: ProcessingProfileControlledValues,
): boolean {
  return (
    values.reviewBeforeRenderEnabled === candidate.reviewBeforeRenderEnabled &&
    values.timelineEditorEnabled === candidate.timelineEditorEnabled &&
    values.transitionsEnabled === candidate.transitionsEnabled &&
    values.transcriptionProvider === candidate.transcriptionProvider &&
    values.whisperModelSize === candidate.whisperModelSize &&
    values.defaultFramingMode === candidate.defaultFramingMode &&
    values.faceDetectionMode === candidate.faceDetectionMode &&
    values.fallbackCropPosition === candidate.fallbackCropPosition &&
    values.faceAnchorProfile === candidate.faceAnchorProfile
  );
}

export function matchesProcessingProfile(
  values: ProcessingProfileControlledValues,
  profile: ProcessingProfile,
): boolean {
  return workflowMatchesValues(values, getProcessingProfileControlledValues(profile));
}

export function matchesSavedWorkflow(values: ProcessingProfileControlledValues, workflow: SavedWorkflow): boolean {
  return workflowMatchesValues(values, getSavedWorkflowControlledValues(workflow));
}

function getSavedWorkflowMatch(
  values: ProcessingProfileControlledValues,
  workflows: SavedWorkflow[],
): SavedWorkflow | null {
  const sorted = [...workflows].sort((left, right) => {
    const rightTime = Date.parse(right.updatedAt);
    const leftTime = Date.parse(left.updatedAt);
    return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
  });

  return sorted.find((workflow) => matchesSavedWorkflow(values, workflow)) ?? null;
}

function getBuiltInWorkflowMatch(values: ProcessingProfileControlledValues): ProcessingProfile | null {
  return BUILT_IN_WORKFLOW_IDS.find((profileId) => matchesProcessingProfile(values, profileId)) ?? null;
}

export function resolveWorkflowSelection(options: {
  values: ProcessingProfileControlledValues;
  savedWorkflows?: SavedWorkflow[];
  persistedSource?: WorkflowSource | null;
  persistedBuiltInProfile?: PersistedProcessingProfile | null;
  persistedSavedWorkflowId?: string | null;
}): WorkflowSelection {
  const {
    values,
    savedWorkflows = [],
    persistedSource = null,
    persistedBuiltInProfile = null,
    persistedSavedWorkflowId = null,
  } = options;
  const persistedSavedMatch =
    persistedSource === "saved" && persistedSavedWorkflowId
      ? savedWorkflows.find((workflow) => workflow.id === persistedSavedWorkflowId) ?? null
      : null;
  if (persistedSavedMatch && matchesSavedWorkflow(values, persistedSavedMatch)) {
    return { kind: "saved", id: persistedSavedMatch.id };
  }

  if (
    persistedSource === "built_in" &&
    persistedBuiltInProfile &&
    persistedBuiltInProfile !== "custom" &&
    matchesProcessingProfile(values, persistedBuiltInProfile)
  ) {
    return { kind: "built_in", id: persistedBuiltInProfile };
  }

  const savedMatch = getSavedWorkflowMatch(values, savedWorkflows);
  if (savedMatch) {
    return { kind: "saved", id: savedMatch.id };
  }

  const builtInMatch = getBuiltInWorkflowMatch(values);
  if (builtInMatch) {
    return { kind: "built_in", id: builtInMatch };
  }

  return { kind: "custom" };
}

export function getWorkflowSelectionLabel(selection: WorkflowSelection, savedWorkflows: SavedWorkflow[] = []): string {
  if (selection.kind === "built_in") {
    return getProcessingProfilePreset(selection.id).label;
  }
  if (selection.kind === "saved") {
    return savedWorkflows.find((workflow) => workflow.id === selection.id)?.name ?? "Saved workflow";
  }
  return "Custom";
}

export function getWorkflowSelectionDescription(
  selection: WorkflowSelection,
  savedWorkflows: SavedWorkflow[] = [],
): string {
  if (selection.kind === "built_in") {
    return getProcessingProfilePreset(selection.id).description;
  }
  if (selection.kind === "saved") {
    return "This task will use the selected saved workflow for workflow, framing, and transcription.";
  }
  return "This task will use your saved workflow, framing, and transcription defaults.";
}

export function getWorkflowSelectionValue(
  selection: WorkflowSelection,
  savedWorkflows: SavedWorkflow[] = [],
): ProcessingProfileControlledValues | null {
  if (selection.kind === "built_in") {
    return getProcessingProfileControlledValues(selection.id);
  }
  if (selection.kind === "saved") {
    const workflow = savedWorkflows.find((entry) => entry.id === selection.id);
    return workflow ? getSavedWorkflowControlledValues(workflow) : null;
  }
  return null;
}

export function applyWorkflowSelection<T extends ProcessingProfileControlledValues>(
  base: T,
  selection: WorkflowSelection,
  savedWorkflows: SavedWorkflow[] = [],
): T {
  const values = getWorkflowSelectionValue(selection, savedWorkflows);
  if (!values) {
    return base;
  }
  return {
    ...base,
    ...values,
  };
}

export function getWorkflowSelectValue(selection: WorkflowSelection): string {
  if (selection.kind === "built_in") {
    return `built_in:${selection.id}`;
  }
  if (selection.kind === "saved") {
    return `saved:${selection.id}`;
  }
  return "custom";
}

export function parseWorkflowSelectValue(rawValue: string): WorkflowSelection {
  const trimmed = rawValue.trim();
  if (trimmed === "custom") {
    return { kind: "custom" };
  }
  if (trimmed.startsWith("built_in:")) {
    const id = trimmed.slice("built_in:".length) as ProcessingProfile;
    if (BUILT_IN_WORKFLOW_IDS.includes(id)) {
      return { kind: "built_in", id };
    }
  }
  if (trimmed.startsWith("saved:")) {
    const id = trimmed.slice("saved:".length).trim();
    if (id) {
      return { kind: "saved", id };
    }
  }
  return { kind: "custom" };
}

export function getWorkflowSelectionMetadata(
  selection: WorkflowSelection,
  savedWorkflows: SavedWorkflow[] = [],
): {
  workflowSource: WorkflowSource;
  processingProfile: PersistedProcessingProfile;
  savedWorkflowId: string | null;
  workflowNameSnapshot: string | null;
} {
  if (selection.kind === "built_in") {
    return {
      workflowSource: "built_in",
      processingProfile: selection.id,
      savedWorkflowId: null,
      workflowNameSnapshot: null,
    };
  }
  if (selection.kind === "saved") {
    const workflow = savedWorkflows.find((entry) => entry.id === selection.id) ?? null;
    return {
      workflowSource: workflow ? "saved" : "custom",
      processingProfile: "custom",
      savedWorkflowId: workflow?.id ?? null,
      workflowNameSnapshot: workflow?.name ?? null,
    };
  }
  return {
    workflowSource: "custom",
    processingProfile: "custom",
    savedWorkflowId: null,
    workflowNameSnapshot: null,
  };
}

export function isWorkflowSelectionEqual(left: WorkflowSelection, right: WorkflowSelection): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "custom" && right.kind === "custom") {
    return true;
  }
  if (left.kind === "built_in" && right.kind === "built_in") {
    return left.id === right.id;
  }
  if (left.kind === "saved" && right.kind === "saved") {
    return left.id === right.id;
  }
  return false;
}

export function workflowSelectionFromBuiltInProfile(profile: PersistedProcessingProfile): WorkflowSelection {
  if (profile === "custom") {
    return { kind: "custom" };
  }
  return { kind: "built_in", id: profile };
}
