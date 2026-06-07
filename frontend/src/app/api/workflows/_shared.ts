import {
  DEFAULT_FRAMING_MODES,
  FACE_ANCHOR_PROFILES,
  FACE_DETECTION_MODES,
  FALLBACK_CROP_POSITIONS,
  TRANSCRIPTION_PROVIDERS,
  WHISPER_MODEL_SIZES,
} from "@/app/settings/settings-section-types";
import type { SavedWorkflow } from "@/lib/processing-profiles";

const VALID_TRANSCRIPTION_PROVIDERS = new Set(TRANSCRIPTION_PROVIDERS);
const VALID_WHISPER_MODEL_SIZES = new Set(WHISPER_MODEL_SIZES);
const VALID_DEFAULT_FRAMING_MODES = new Set(DEFAULT_FRAMING_MODES);
const VALID_FACE_DETECTION_MODES = new Set(FACE_DETECTION_MODES);
const VALID_FALLBACK_CROP_POSITIONS = new Set(FALLBACK_CROP_POSITIONS);
const VALID_FACE_ANCHOR_PROFILES = new Set(FACE_ANCHOR_PROFILES);

type SavedWorkflowRecord = {
  id: string;
  name: string;
  review_before_render_enabled: boolean;
  timeline_editor_enabled: boolean;
  transitions_enabled: boolean;
  transcription_provider: string;
  whisper_model_size: string;
  default_framing_mode: string;
  face_detection_mode: string;
  fallback_crop_position: string;
  face_anchor_profile: string;
  created_at: Date | string;
  updated_at: Date | string;
};

function asTimestamp(value: Date | string): string {
  return value instanceof Date ? value.toISOString() : new Date(value).toISOString();
}

export function serializeSavedWorkflow(record: SavedWorkflowRecord): SavedWorkflow {
  return {
    id: record.id,
    name: record.name,
    reviewBeforeRenderEnabled: Boolean(record.review_before_render_enabled),
    timelineEditorEnabled: Boolean(record.timeline_editor_enabled),
    transitionsEnabled: Boolean(record.transitions_enabled),
    transcriptionProvider: VALID_TRANSCRIPTION_PROVIDERS.has(record.transcription_provider as any)
      ? (record.transcription_provider as SavedWorkflow["transcriptionProvider"])
      : "local",
    whisperModelSize: VALID_WHISPER_MODEL_SIZES.has(record.whisper_model_size as any)
      ? (record.whisper_model_size as SavedWorkflow["whisperModelSize"])
      : "medium",
    defaultFramingMode: VALID_DEFAULT_FRAMING_MODES.has(record.default_framing_mode as any)
      ? (record.default_framing_mode as SavedWorkflow["defaultFramingMode"])
      : "auto",
    faceDetectionMode: VALID_FACE_DETECTION_MODES.has(record.face_detection_mode as any)
      ? (record.face_detection_mode as SavedWorkflow["faceDetectionMode"])
      : "balanced",
    fallbackCropPosition: VALID_FALLBACK_CROP_POSITIONS.has(record.fallback_crop_position as any)
      ? (record.fallback_crop_position as SavedWorkflow["fallbackCropPosition"])
      : "center",
    faceAnchorProfile: VALID_FACE_ANCHOR_PROFILES.has(record.face_anchor_profile as any)
      ? (record.face_anchor_profile as SavedWorkflow["faceAnchorProfile"])
      : "auto",
    createdAt: asTimestamp(record.created_at),
    updatedAt: asTimestamp(record.updated_at),
  };
}

export function validateWorkflowName(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed.length < 1 || trimmed.length > 120) {
    return null;
  }
  return trimmed;
}

export function validateWorkflowValues(body: Record<string, unknown>): {
  review_before_render_enabled: boolean;
  timeline_editor_enabled: boolean;
  transitions_enabled: boolean;
  transcription_provider: SavedWorkflow["transcriptionProvider"];
  whisper_model_size: SavedWorkflow["whisperModelSize"];
  default_framing_mode: SavedWorkflow["defaultFramingMode"];
  face_detection_mode: SavedWorkflow["faceDetectionMode"];
  fallback_crop_position: SavedWorkflow["fallbackCropPosition"];
  face_anchor_profile: SavedWorkflow["faceAnchorProfile"];
} | null {
  const {
    reviewBeforeRenderEnabled,
    timelineEditorEnabled,
    transitionsEnabled,
    transcriptionProvider,
    whisperModelSize,
    defaultFramingMode,
    faceDetectionMode,
    fallbackCropPosition,
    faceAnchorProfile,
  } = body;

  if (
    typeof reviewBeforeRenderEnabled !== "boolean" ||
    typeof timelineEditorEnabled !== "boolean" ||
    typeof transitionsEnabled !== "boolean" ||
    typeof transcriptionProvider !== "string" ||
    typeof whisperModelSize !== "string" ||
    typeof defaultFramingMode !== "string" ||
    typeof faceDetectionMode !== "string" ||
    typeof fallbackCropPosition !== "string" ||
    typeof faceAnchorProfile !== "string"
  ) {
    return null;
  }

  if (
    !VALID_TRANSCRIPTION_PROVIDERS.has(transcriptionProvider as any) ||
    !VALID_WHISPER_MODEL_SIZES.has(whisperModelSize as any) ||
    !VALID_DEFAULT_FRAMING_MODES.has(defaultFramingMode as any) ||
    !VALID_FACE_DETECTION_MODES.has(faceDetectionMode as any) ||
    !VALID_FALLBACK_CROP_POSITIONS.has(fallbackCropPosition as any) ||
    !VALID_FACE_ANCHOR_PROFILES.has(faceAnchorProfile as any)
  ) {
    return null;
  }

  return {
    review_before_render_enabled: reviewBeforeRenderEnabled,
    timeline_editor_enabled: timelineEditorEnabled,
    transitions_enabled: transitionsEnabled,
    transcription_provider: transcriptionProvider as SavedWorkflow["transcriptionProvider"],
    whisper_model_size: whisperModelSize as SavedWorkflow["whisperModelSize"],
    default_framing_mode: defaultFramingMode as SavedWorkflow["defaultFramingMode"],
    face_detection_mode: faceDetectionMode as SavedWorkflow["faceDetectionMode"],
    fallback_crop_position: fallbackCropPosition as SavedWorkflow["fallbackCropPosition"],
    face_anchor_profile: faceAnchorProfile as SavedWorkflow["faceAnchorProfile"],
  };
}
