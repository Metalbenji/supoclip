import type {
  DefaultFramingMode,
  FaceDetectionMode,
  FallbackCropPosition,
  ProcessingProfile,
} from "@/app/settings/settings-section-types";

export interface ProcessingProfilePreset {
  id: ProcessingProfile;
  label: string;
  description: string;
  reviewBeforeRenderEnabled: boolean;
  timelineEditorEnabled: boolean;
  transitionsEnabled: boolean;
  transcriptionProvider: "local" | "assemblyai";
  whisperModelSize: "tiny" | "base" | "small" | "medium" | "large" | "turbo";
  defaultFramingMode: DefaultFramingMode;
  faceDetectionMode: FaceDetectionMode;
  fallbackCropPosition: FallbackCropPosition;
}

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
  },
};

export function getProcessingProfilePreset(profile: ProcessingProfile): ProcessingProfilePreset {
  return PROCESSING_PROFILE_PRESETS[profile] ?? PROCESSING_PROFILE_PRESETS.balanced;
}
