import { NextRequest, NextResponse } from "next/server";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import prisma from "@/lib/prisma";
import {
  DEFAULT_FONT_STYLE_OPTIONS,
  isHexColor,
  isTextAlign,
  isTextTransform,
  normalizeFontSize,
  normalizeFontWeight,
  normalizeLetterSpacing,
  normalizeLineHeight,
  normalizeShadowBlur,
  normalizeShadowOffset,
  normalizeShadowOpacity,
  normalizeStrokeBlur,
  normalizeStrokeWidth,
} from "@/lib/font-style-options";

const SUPPORTED_TRANSCRIPTION_PROVIDERS = new Set(["local", "assemblyai"]);
const SUPPORTED_WHISPER_DEVICES = new Set(["auto", "cpu", "gpu"]);
const SUPPORTED_WHISPER_MODEL_SIZES = new Set(["tiny", "base", "small", "medium", "large", "turbo"]);
const SUPPORTED_DEFAULT_FRAMING_MODES = new Set(["auto", "prefer_face", "fixed_position"]);
const SUPPORTED_FACE_DETECTION_MODES = new Set(["balanced", "more_faces"]);
const SUPPORTED_FALLBACK_CROP_POSITIONS = new Set(["center", "left_center", "right_center"]);
const SUPPORTED_FACE_ANCHOR_PROFILES = new Set([
  "auto",
  "left_only",
  "left_or_center",
  "center_only",
  "right_or_center",
  "right_only",
]);
const SUPPORTED_PROCESSING_PROFILES = new Set(["fast_draft", "balanced", "best_quality", "stream_layout"]);
const SUPPORTED_AI_PROVIDERS = new Set(["openai", "google", "anthropic", "zai", "ollama"]);
const MIN_WHISPER_CHUNK_DURATION_SECONDS = 300;
const MAX_WHISPER_CHUNK_DURATION_SECONDS = 3600;
const MIN_WHISPER_CHUNK_OVERLAP_SECONDS = 0;
const MAX_WHISPER_CHUNK_OVERLAP_SECONDS = 120;
const MIN_TASK_TIMEOUT_SECONDS = 300;
const MAX_TASK_TIMEOUT_SECONDS = 86400;

type WhisperPreferenceRow = {
  default_whisper_model_size: string | null;
  default_whisper_device: string | null;
  default_whisper_gpu_index: number | null;
};

type FaceAnchorPreferenceRow = {
  default_face_anchor_profile: string | null;
};

async function getStoredWhisperPreferences(userId: string): Promise<WhisperPreferenceRow> {
  const rows = await prisma.$queryRaw<WhisperPreferenceRow[]>`
    SELECT
      "default_whisper_model_size",
      "default_whisper_device",
      "default_whisper_gpu_index"
    FROM "users"
    WHERE "id" = ${userId}
    LIMIT 1
  `;

  return rows[0] ?? {
    default_whisper_model_size: null,
    default_whisper_device: null,
    default_whisper_gpu_index: null,
  };
}

async function updateStoredWhisperPreferences(
  userId: string,
  whisperModelSize: string | undefined,
  whisperDevice: string | undefined,
  whisperGpuIndex: number | null | undefined,
): Promise<void> {
  if (whisperModelSize === undefined && whisperDevice === undefined && whisperGpuIndex === undefined) {
    return;
  }

  await prisma.$executeRaw`
    UPDATE "users"
    SET
      "default_whisper_model_size" = CASE
        WHEN ${whisperModelSize !== undefined}
          THEN CAST(${whisperModelSize ?? null} AS VARCHAR(20))
        ELSE "default_whisper_model_size"
      END,
      "default_whisper_device" = CASE
        WHEN ${whisperDevice !== undefined}
          THEN CAST(${whisperDevice ?? null} AS VARCHAR(20))
        ELSE "default_whisper_device"
      END,
      "default_whisper_gpu_index" = CASE
        WHEN ${whisperGpuIndex !== undefined}
          THEN CAST(${whisperGpuIndex} AS INTEGER)
        ELSE "default_whisper_gpu_index"
      END
    WHERE "id" = ${userId}
  `;
}

async function getStoredFaceAnchorPreference(userId: string): Promise<FaceAnchorPreferenceRow> {
  const rows = await prisma.$queryRaw<FaceAnchorPreferenceRow[]>`
    SELECT
      "default_face_anchor_profile"
    FROM "users"
    WHERE "id" = ${userId}
    LIMIT 1
  `;

  return rows[0] ?? {
    default_face_anchor_profile: null,
  };
}

async function updateStoredFaceAnchorPreference(
  userId: string,
  faceAnchorProfile: string | undefined,
): Promise<void> {
  if (faceAnchorProfile === undefined) {
    return;
  }

  await prisma.$executeRaw`
    UPDATE "users"
    SET
      "default_face_anchor_profile" = CAST(${faceAnchorProfile ?? "auto"} AS VARCHAR(24))
    WHERE "id" = ${userId}
  `;
}

function normalizeDefaultFramingMode(rawValue: unknown): "auto" | "prefer_face" | "fixed_position" {
  const normalized = typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
  if (normalized === "disable_face_crop") {
    return "fixed_position";
  }
  if (SUPPORTED_DEFAULT_FRAMING_MODES.has(normalized)) {
    return normalized as "auto" | "prefer_face" | "fixed_position";
  }
  return "auto";
}

function normalizeFaceDetectionMode(rawValue: unknown): "balanced" | "more_faces" {
  const normalized = typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
  if (normalized === "center_only") {
    return "balanced";
  }
  if (SUPPORTED_FACE_DETECTION_MODES.has(normalized)) {
    return normalized as "balanced" | "more_faces";
  }
  return "balanced";
}

function normalizeFallbackCropPosition(rawValue: unknown): "center" | "left_center" | "right_center" {
  const normalized = typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
  if (SUPPORTED_FALLBACK_CROP_POSITIONS.has(normalized)) {
    return normalized as "center" | "left_center" | "right_center";
  }
  return "center";
}

function normalizeFaceAnchorProfile(
  rawValue: unknown,
): "auto" | "left_only" | "left_or_center" | "center_only" | "right_or_center" | "right_only" {
  const normalized = typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
  if (SUPPORTED_FACE_ANCHOR_PROFILES.has(normalized)) {
    return normalized as "auto" | "left_only" | "left_or_center" | "center_only" | "right_or_center" | "right_only";
  }
  return "auto";
}

function normalizeProcessingProfile(rawValue: unknown): "fast_draft" | "balanced" | "best_quality" | "stream_layout" {
  const normalized = typeof rawValue === "string" ? rawValue.trim().toLowerCase() : "";
  if (SUPPORTED_PROCESSING_PROFILES.has(normalized)) {
    return normalized as "fast_draft" | "balanced" | "best_quality" | "stream_layout";
  }
  return "balanced";
}

// GET /api/preferences - Get user preferences
export async function GET() {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const user = await (prisma.user as any).findUnique({
      where: { id: session.user.id },
      select: {
        default_font_family: true,
        default_font_size: true,
        default_font_color: true,
        default_highlight_color: true,
        default_font_weight: true,
        default_line_height: true,
        default_letter_spacing: true,
        default_text_transform: true,
        default_text_align: true,
        default_stroke_color: true,
        default_stroke_width: true,
        default_stroke_blur: true,
        default_shadow_color: true,
        default_shadow_opacity: true,
        default_shadow_blur: true,
        default_shadow_offset_x: true,
        default_shadow_offset_y: true,
        default_transitions_enabled: true,
        default_review_before_render_enabled: true,
        default_timeline_editor_enabled: true,
        default_processing_profile: true,
        default_framing_mode: true,
        default_face_detection_mode: true,
        default_fallback_crop_position: true,
        default_transcription_provider: true,
        default_whisper_chunking_enabled: true,
        default_whisper_chunk_duration_seconds: true,
        default_whisper_chunk_overlap_seconds: true,
        default_task_timeout_seconds: true,
        default_ai_provider: true,
        default_ai_model: true,
      },
    });

    if (!user) {
      return NextResponse.json({ error: "User not found" }, { status: 404 });
    }

    const textTransform = isTextTransform(user.default_text_transform)
      ? user.default_text_transform
      : DEFAULT_FONT_STYLE_OPTIONS.textTransform;
    const textAlign = isTextAlign(user.default_text_align)
      ? user.default_text_align
      : DEFAULT_FONT_STYLE_OPTIONS.textAlign;
    const whisperPreferences = await getStoredWhisperPreferences(session.user.id);
    const faceAnchorPreference = await getStoredFaceAnchorPreference(session.user.id);
    const hadLegacyCenterOnly = typeof user.default_face_detection_mode === "string" && user.default_face_detection_mode === "center_only";
    const defaultFramingMode = hadLegacyCenterOnly
      ? "fixed_position"
      : normalizeDefaultFramingMode(user.default_framing_mode);

    return NextResponse.json({
      fontFamily: user.default_font_family || DEFAULT_FONT_STYLE_OPTIONS.fontFamily,
      fontSize: normalizeFontSize(user.default_font_size || DEFAULT_FONT_STYLE_OPTIONS.fontSize),
      fontColor: isHexColor(user.default_font_color)
        ? user.default_font_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.fontColor,
      highlightColor: isHexColor(user.default_highlight_color)
        ? user.default_highlight_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.highlightColor,
      fontWeight: normalizeFontWeight(user.default_font_weight),
      lineHeight: normalizeLineHeight(user.default_line_height),
      letterSpacing: normalizeLetterSpacing(user.default_letter_spacing),
      textTransform,
      textAlign,
      strokeColor: isHexColor(user.default_stroke_color)
        ? user.default_stroke_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.strokeColor,
      strokeWidth: normalizeStrokeWidth(user.default_stroke_width),
      strokeBlur: normalizeStrokeBlur(user.default_stroke_blur),
      shadowColor: isHexColor(user.default_shadow_color)
        ? user.default_shadow_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.shadowColor,
      shadowOpacity: normalizeShadowOpacity(user.default_shadow_opacity),
      shadowBlur: normalizeShadowBlur(user.default_shadow_blur),
      shadowOffsetX: normalizeShadowOffset(user.default_shadow_offset_x),
      shadowOffsetY: normalizeShadowOffset(user.default_shadow_offset_y),
      transitionsEnabled: user.default_transitions_enabled ?? false,
      reviewBeforeRenderEnabled: user.default_review_before_render_enabled ?? true,
      timelineEditorEnabled: user.default_timeline_editor_enabled ?? true,
      defaultProcessingProfile: normalizeProcessingProfile(user.default_processing_profile),
      defaultFramingMode,
      faceDetectionMode: normalizeFaceDetectionMode(user.default_face_detection_mode),
      fallbackCropPosition: normalizeFallbackCropPosition(user.default_fallback_crop_position),
      faceAnchorProfile: normalizeFaceAnchorProfile(faceAnchorPreference.default_face_anchor_profile),
      transcriptionProvider: user.default_transcription_provider || "local",
      whisperChunkingEnabled: user.default_whisper_chunking_enabled ?? true,
      whisperChunkDurationSeconds: user.default_whisper_chunk_duration_seconds || 1200,
      whisperChunkOverlapSeconds: user.default_whisper_chunk_overlap_seconds || 8,
      taskTimeoutSeconds: user.default_task_timeout_seconds || 21600,
      whisperModelSize:
        typeof whisperPreferences.default_whisper_model_size === "string" &&
        SUPPORTED_WHISPER_MODEL_SIZES.has(whisperPreferences.default_whisper_model_size)
          ? whisperPreferences.default_whisper_model_size
          : "medium",
      whisperDevice:
        typeof whisperPreferences.default_whisper_device === "string" &&
        SUPPORTED_WHISPER_DEVICES.has(whisperPreferences.default_whisper_device)
          ? whisperPreferences.default_whisper_device
          : "auto",
      whisperGpuIndex:
        typeof whisperPreferences.default_whisper_gpu_index === "number" &&
        Number.isInteger(whisperPreferences.default_whisper_gpu_index)
          ? whisperPreferences.default_whisper_gpu_index
          : null,
      aiProvider: user.default_ai_provider || "openai",
      aiModel: user.default_ai_model || "",
    });
  } catch (error) {
    console.error("Error fetching preferences:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}

function isIntegerInRange(value: unknown, min: number, max: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
}

function isNumberInRange(value: unknown, min: number, max: number): boolean {
  return typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
}

// PATCH /api/preferences - Update user preferences
export async function PATCH(request: NextRequest) {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const {
      fontFamily,
      fontSize,
      fontColor,
      highlightColor,
      fontWeight,
      lineHeight,
      letterSpacing,
      textTransform,
      textAlign,
      strokeColor,
      strokeWidth,
      strokeBlur,
      shadowColor,
      shadowOpacity,
      shadowBlur,
      shadowOffsetX,
      shadowOffsetY,
      transitionsEnabled,
      reviewBeforeRenderEnabled,
      timelineEditorEnabled,
      defaultProcessingProfile,
      defaultFramingMode,
      faceDetectionMode,
      fallbackCropPosition,
      faceAnchorProfile,
      transcriptionProvider,
      whisperChunkingEnabled,
      whisperChunkDurationSeconds,
      whisperChunkOverlapSeconds,
      taskTimeoutSeconds,
      whisperModelSize,
      whisperDevice,
      whisperGpuIndex,
      aiProvider,
      aiModel,
    } = body;

    if (fontFamily !== undefined && typeof fontFamily !== "string") {
      return NextResponse.json({ error: "Invalid fontFamily" }, { status: 400 });
    }
    if (fontSize !== undefined && !isNumberInRange(fontSize, 24, 48)) {
      return NextResponse.json({ error: "Invalid fontSize (must be between 24 and 48)" }, { status: 400 });
    }
    if (fontColor !== undefined && !isHexColor(fontColor)) {
      return NextResponse.json({ error: "Invalid fontColor (must be hex format like #FFFFFF)" }, { status: 400 });
    }
    if (highlightColor !== undefined && !isHexColor(highlightColor)) {
      return NextResponse.json(
        { error: "Invalid highlightColor (must be hex format like #FDE047)" },
        { status: 400 },
      );
    }
    if (fontWeight !== undefined && !isIntegerInRange(fontWeight, 300, 900)) {
      return NextResponse.json({ error: "Invalid fontWeight (must be an integer from 300 to 900)" }, { status: 400 });
    }
    if (lineHeight !== undefined && !isNumberInRange(lineHeight, 1, 2)) {
      return NextResponse.json({ error: "Invalid lineHeight (must be between 1.0 and 2.0)" }, { status: 400 });
    }
    if (letterSpacing !== undefined && !isIntegerInRange(letterSpacing, 0, 6)) {
      return NextResponse.json({ error: "Invalid letterSpacing (must be an integer from 0 to 6)" }, { status: 400 });
    }
    if (textTransform !== undefined && !isTextTransform(textTransform)) {
      return NextResponse.json(
        { error: "Invalid textTransform (must be none, uppercase, lowercase, or capitalize)" },
        { status: 400 },
      );
    }
    if (textAlign !== undefined && !isTextAlign(textAlign)) {
      return NextResponse.json({ error: "Invalid textAlign (must be left, center, or right)" }, { status: 400 });
    }
    if (strokeColor !== undefined && !isHexColor(strokeColor)) {
      return NextResponse.json({ error: "Invalid strokeColor (must be hex format like #000000)" }, { status: 400 });
    }
    if (strokeWidth !== undefined && !isIntegerInRange(strokeWidth, 0, 8)) {
      return NextResponse.json({ error: "Invalid strokeWidth (must be an integer from 0 to 8)" }, { status: 400 });
    }
    if (strokeBlur !== undefined && !isNumberInRange(strokeBlur, 0, 4)) {
      return NextResponse.json({ error: "Invalid strokeBlur (must be a number from 0 to 4)" }, { status: 400 });
    }
    if (shadowColor !== undefined && !isHexColor(shadowColor)) {
      return NextResponse.json({ error: "Invalid shadowColor (must be hex format like #000000)" }, { status: 400 });
    }
    if (shadowOpacity !== undefined && !isNumberInRange(shadowOpacity, 0, 1)) {
      return NextResponse.json({ error: "Invalid shadowOpacity (must be between 0 and 1)" }, { status: 400 });
    }
    if (shadowBlur !== undefined && !isIntegerInRange(shadowBlur, 0, 8)) {
      return NextResponse.json({ error: "Invalid shadowBlur (must be an integer from 0 to 8)" }, { status: 400 });
    }
    if (shadowOffsetX !== undefined && !isIntegerInRange(shadowOffsetX, -12, 12)) {
      return NextResponse.json(
        { error: "Invalid shadowOffsetX (must be an integer from -12 to 12)" },
        { status: 400 },
      );
    }
    if (shadowOffsetY !== undefined && !isIntegerInRange(shadowOffsetY, -12, 12)) {
      return NextResponse.json(
        { error: "Invalid shadowOffsetY (must be an integer from -12 to 12)" },
        { status: 400 },
      );
    }
    if (transitionsEnabled !== undefined && typeof transitionsEnabled !== "boolean") {
      return NextResponse.json({ error: "Invalid transitionsEnabled" }, { status: 400 });
    }
    if (reviewBeforeRenderEnabled !== undefined && typeof reviewBeforeRenderEnabled !== "boolean") {
      return NextResponse.json({ error: "Invalid reviewBeforeRenderEnabled" }, { status: 400 });
    }
    if (timelineEditorEnabled !== undefined && typeof timelineEditorEnabled !== "boolean") {
      return NextResponse.json({ error: "Invalid timelineEditorEnabled" }, { status: 400 });
    }
    if (
      defaultProcessingProfile !== undefined &&
      (typeof defaultProcessingProfile !== "string" || !SUPPORTED_PROCESSING_PROFILES.has(defaultProcessingProfile))
    ) {
      return NextResponse.json(
        { error: "Invalid defaultProcessingProfile" },
        { status: 400 },
      );
    }
    if (
      defaultFramingMode !== undefined &&
      (typeof defaultFramingMode !== "string" || !SUPPORTED_DEFAULT_FRAMING_MODES.has(defaultFramingMode))
    ) {
      return NextResponse.json(
        { error: "Invalid defaultFramingMode (must be auto, prefer_face, or fixed_position)" },
        { status: 400 },
      );
    }
    if (
      faceDetectionMode !== undefined &&
      (typeof faceDetectionMode !== "string" || !SUPPORTED_FACE_DETECTION_MODES.has(faceDetectionMode))
    ) {
      return NextResponse.json(
        { error: "Invalid faceDetectionMode (must be balanced or more_faces)" },
        { status: 400 },
      );
    }
    if (
      fallbackCropPosition !== undefined &&
      (typeof fallbackCropPosition !== "string" || !SUPPORTED_FALLBACK_CROP_POSITIONS.has(fallbackCropPosition))
    ) {
      return NextResponse.json(
        { error: "Invalid fallbackCropPosition (must be center, left_center, or right_center)" },
        { status: 400 },
      );
    }
    if (
      faceAnchorProfile !== undefined &&
      (typeof faceAnchorProfile !== "string" || !SUPPORTED_FACE_ANCHOR_PROFILES.has(faceAnchorProfile))
    ) {
      return NextResponse.json(
        { error: "Invalid faceAnchorProfile (must be auto, left_only, left_or_center, center_only, right_or_center, or right_only)" },
        { status: 400 },
      );
    }
    if (
      transcriptionProvider !== undefined &&
      (typeof transcriptionProvider !== "string" || !SUPPORTED_TRANSCRIPTION_PROVIDERS.has(transcriptionProvider))
    ) {
      return NextResponse.json(
        { error: "Invalid transcriptionProvider (must be local or assemblyai)" },
        { status: 400 },
      );
    }
    if (aiProvider !== undefined && (typeof aiProvider !== "string" || !SUPPORTED_AI_PROVIDERS.has(aiProvider))) {
      return NextResponse.json(
        { error: "Invalid aiProvider (must be openai, google, anthropic, zai, or ollama)" },
        { status: 400 },
      );
    }
    if (aiModel !== undefined && aiModel !== null && typeof aiModel !== "string") {
      return NextResponse.json({ error: "Invalid aiModel (must be a string or null)" }, { status: 400 });
    }
    if (whisperChunkingEnabled !== undefined && typeof whisperChunkingEnabled !== "boolean") {
      return NextResponse.json({ error: "Invalid whisperChunkingEnabled" }, { status: 400 });
    }
    if (
      whisperChunkDurationSeconds !== undefined &&
      !isIntegerInRange(
        whisperChunkDurationSeconds,
        MIN_WHISPER_CHUNK_DURATION_SECONDS,
        MAX_WHISPER_CHUNK_DURATION_SECONDS,
      )
    ) {
      return NextResponse.json(
        {
          error: `Invalid whisperChunkDurationSeconds (must be an integer from ${MIN_WHISPER_CHUNK_DURATION_SECONDS} to ${MAX_WHISPER_CHUNK_DURATION_SECONDS})`,
        },
        { status: 400 },
      );
    }
    if (
      whisperChunkOverlapSeconds !== undefined &&
      !isIntegerInRange(
        whisperChunkOverlapSeconds,
        MIN_WHISPER_CHUNK_OVERLAP_SECONDS,
        MAX_WHISPER_CHUNK_OVERLAP_SECONDS,
      )
    ) {
      return NextResponse.json(
        {
          error: `Invalid whisperChunkOverlapSeconds (must be an integer from ${MIN_WHISPER_CHUNK_OVERLAP_SECONDS} to ${MAX_WHISPER_CHUNK_OVERLAP_SECONDS})`,
        },
        { status: 400 },
      );
    }
    if (
      taskTimeoutSeconds !== undefined &&
      !isIntegerInRange(taskTimeoutSeconds, MIN_TASK_TIMEOUT_SECONDS, MAX_TASK_TIMEOUT_SECONDS)
    ) {
      return NextResponse.json(
        {
          error: `Invalid taskTimeoutSeconds (must be an integer from ${MIN_TASK_TIMEOUT_SECONDS} to ${MAX_TASK_TIMEOUT_SECONDS})`,
        },
        { status: 400 },
      );
    }
    if (
      whisperModelSize !== undefined &&
      (typeof whisperModelSize !== "string" || !SUPPORTED_WHISPER_MODEL_SIZES.has(whisperModelSize))
    ) {
      return NextResponse.json(
        { error: "Invalid whisperModelSize (must be tiny, base, small, medium, large, or turbo)" },
        { status: 400 },
      );
    }
    if (
      whisperDevice !== undefined &&
      (typeof whisperDevice !== "string" || !SUPPORTED_WHISPER_DEVICES.has(whisperDevice))
    ) {
      return NextResponse.json(
        { error: "Invalid whisperDevice (must be auto, cpu, or gpu)" },
        { status: 400 },
      );
    }
    if (
      whisperGpuIndex !== undefined &&
      whisperGpuIndex !== null &&
      !isIntegerInRange(whisperGpuIndex, 0, Number.MAX_SAFE_INTEGER)
    ) {
      return NextResponse.json(
        { error: "Invalid whisperGpuIndex (must be a non-negative integer or null)" },
        { status: 400 },
      );
    }
    if (
      whisperChunkDurationSeconds !== undefined &&
      whisperChunkOverlapSeconds !== undefined &&
      whisperChunkOverlapSeconds >= whisperChunkDurationSeconds
    ) {
      return NextResponse.json(
        { error: "Invalid whisperChunkOverlapSeconds (must be smaller than whisperChunkDurationSeconds)" },
        { status: 400 },
      );
    }

    const updatedUser = await (prisma.user as any).update({
      where: { id: session.user.id },
      data: {
        ...(fontFamily !== undefined && { default_font_family: fontFamily.trim() || DEFAULT_FONT_STYLE_OPTIONS.fontFamily }),
        ...(fontSize !== undefined && { default_font_size: normalizeFontSize(fontSize) }),
        ...(fontColor !== undefined && { default_font_color: fontColor.toUpperCase() }),
        ...(highlightColor !== undefined && { default_highlight_color: highlightColor.toUpperCase() }),
        ...(fontWeight !== undefined && { default_font_weight: normalizeFontWeight(fontWeight) }),
        ...(lineHeight !== undefined && { default_line_height: normalizeLineHeight(lineHeight) }),
        ...(letterSpacing !== undefined && { default_letter_spacing: normalizeLetterSpacing(letterSpacing) }),
        ...(textTransform !== undefined && { default_text_transform: textTransform }),
        ...(textAlign !== undefined && { default_text_align: textAlign }),
        ...(strokeColor !== undefined && { default_stroke_color: strokeColor.toUpperCase() }),
        ...(strokeWidth !== undefined && { default_stroke_width: normalizeStrokeWidth(strokeWidth) }),
        ...(strokeBlur !== undefined && { default_stroke_blur: normalizeStrokeBlur(strokeBlur) }),
        ...(shadowColor !== undefined && { default_shadow_color: shadowColor.toUpperCase() }),
        ...(shadowOpacity !== undefined && { default_shadow_opacity: normalizeShadowOpacity(shadowOpacity) }),
        ...(shadowBlur !== undefined && { default_shadow_blur: normalizeShadowBlur(shadowBlur) }),
        ...(shadowOffsetX !== undefined && { default_shadow_offset_x: normalizeShadowOffset(shadowOffsetX) }),
        ...(shadowOffsetY !== undefined && { default_shadow_offset_y: normalizeShadowOffset(shadowOffsetY) }),
        ...(transitionsEnabled !== undefined && { default_transitions_enabled: transitionsEnabled }),
        ...(reviewBeforeRenderEnabled !== undefined && {
          default_review_before_render_enabled: reviewBeforeRenderEnabled,
        }),
        ...(timelineEditorEnabled !== undefined && { default_timeline_editor_enabled: timelineEditorEnabled }),
        ...(defaultProcessingProfile !== undefined && { default_processing_profile: defaultProcessingProfile }),
        ...(defaultFramingMode !== undefined && { default_framing_mode: defaultFramingMode }),
        ...(faceDetectionMode !== undefined && { default_face_detection_mode: faceDetectionMode }),
        ...(fallbackCropPosition !== undefined && { default_fallback_crop_position: fallbackCropPosition }),
        ...(transcriptionProvider !== undefined && { default_transcription_provider: transcriptionProvider }),
        ...(whisperChunkingEnabled !== undefined && { default_whisper_chunking_enabled: whisperChunkingEnabled }),
        ...(whisperChunkDurationSeconds !== undefined && {
          default_whisper_chunk_duration_seconds: whisperChunkDurationSeconds,
        }),
        ...(whisperChunkOverlapSeconds !== undefined && {
          default_whisper_chunk_overlap_seconds: whisperChunkOverlapSeconds,
        }),
        ...(taskTimeoutSeconds !== undefined && { default_task_timeout_seconds: taskTimeoutSeconds }),
        ...(aiProvider !== undefined && { default_ai_provider: aiProvider }),
        ...(aiModel !== undefined && { default_ai_model: aiModel || null }),
      },
      select: {
        default_font_family: true,
        default_font_size: true,
        default_font_color: true,
        default_highlight_color: true,
        default_font_weight: true,
        default_line_height: true,
        default_letter_spacing: true,
        default_text_transform: true,
        default_text_align: true,
        default_stroke_color: true,
        default_stroke_width: true,
        default_stroke_blur: true,
        default_shadow_color: true,
        default_shadow_opacity: true,
        default_shadow_blur: true,
        default_shadow_offset_x: true,
        default_shadow_offset_y: true,
        default_transitions_enabled: true,
        default_review_before_render_enabled: true,
        default_timeline_editor_enabled: true,
        default_processing_profile: true,
        default_framing_mode: true,
        default_face_detection_mode: true,
        default_fallback_crop_position: true,
        default_transcription_provider: true,
        default_whisper_chunking_enabled: true,
        default_whisper_chunk_duration_seconds: true,
        default_whisper_chunk_overlap_seconds: true,
        default_task_timeout_seconds: true,
        default_ai_provider: true,
        default_ai_model: true,
      },
    });

    await updateStoredWhisperPreferences(session.user.id, whisperModelSize, whisperDevice, whisperGpuIndex);
    await updateStoredFaceAnchorPreference(session.user.id, faceAnchorProfile);
    const whisperPreferences = await getStoredWhisperPreferences(session.user.id);
    const faceAnchorPreference = await getStoredFaceAnchorPreference(session.user.id);
    const hadLegacyCenterOnly = typeof updatedUser.default_face_detection_mode === "string" && updatedUser.default_face_detection_mode === "center_only";

    return NextResponse.json({
      fontFamily: updatedUser.default_font_family || DEFAULT_FONT_STYLE_OPTIONS.fontFamily,
      fontSize: normalizeFontSize(updatedUser.default_font_size || DEFAULT_FONT_STYLE_OPTIONS.fontSize),
      fontColor: isHexColor(updatedUser.default_font_color)
        ? updatedUser.default_font_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.fontColor,
      highlightColor: isHexColor(updatedUser.default_highlight_color)
        ? updatedUser.default_highlight_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.highlightColor,
      fontWeight: normalizeFontWeight(updatedUser.default_font_weight),
      lineHeight: normalizeLineHeight(updatedUser.default_line_height),
      letterSpacing: normalizeLetterSpacing(updatedUser.default_letter_spacing),
      textTransform: isTextTransform(updatedUser.default_text_transform)
        ? updatedUser.default_text_transform
        : DEFAULT_FONT_STYLE_OPTIONS.textTransform,
      textAlign: isTextAlign(updatedUser.default_text_align)
        ? updatedUser.default_text_align
        : DEFAULT_FONT_STYLE_OPTIONS.textAlign,
      strokeColor: isHexColor(updatedUser.default_stroke_color)
        ? updatedUser.default_stroke_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.strokeColor,
      strokeWidth: normalizeStrokeWidth(updatedUser.default_stroke_width),
      strokeBlur: normalizeStrokeBlur(updatedUser.default_stroke_blur),
      shadowColor: isHexColor(updatedUser.default_shadow_color)
        ? updatedUser.default_shadow_color.toUpperCase()
        : DEFAULT_FONT_STYLE_OPTIONS.shadowColor,
      shadowOpacity: normalizeShadowOpacity(updatedUser.default_shadow_opacity),
      shadowBlur: normalizeShadowBlur(updatedUser.default_shadow_blur),
      shadowOffsetX: normalizeShadowOffset(updatedUser.default_shadow_offset_x),
      shadowOffsetY: normalizeShadowOffset(updatedUser.default_shadow_offset_y),
      transitionsEnabled: updatedUser.default_transitions_enabled ?? false,
      reviewBeforeRenderEnabled: updatedUser.default_review_before_render_enabled ?? true,
      timelineEditorEnabled: updatedUser.default_timeline_editor_enabled ?? true,
      defaultProcessingProfile: normalizeProcessingProfile(updatedUser.default_processing_profile),
      defaultFramingMode: hadLegacyCenterOnly
        ? "fixed_position"
        : normalizeDefaultFramingMode(updatedUser.default_framing_mode),
      faceDetectionMode: normalizeFaceDetectionMode(updatedUser.default_face_detection_mode),
      fallbackCropPosition: normalizeFallbackCropPosition(updatedUser.default_fallback_crop_position),
      faceAnchorProfile: normalizeFaceAnchorProfile(faceAnchorPreference.default_face_anchor_profile),
      transcriptionProvider: updatedUser.default_transcription_provider || "local",
      whisperChunkingEnabled: updatedUser.default_whisper_chunking_enabled ?? true,
      whisperChunkDurationSeconds: updatedUser.default_whisper_chunk_duration_seconds || 1200,
      whisperChunkOverlapSeconds: updatedUser.default_whisper_chunk_overlap_seconds || 8,
      taskTimeoutSeconds: updatedUser.default_task_timeout_seconds || 21600,
      whisperModelSize:
        typeof whisperPreferences.default_whisper_model_size === "string" &&
        SUPPORTED_WHISPER_MODEL_SIZES.has(whisperPreferences.default_whisper_model_size)
          ? whisperPreferences.default_whisper_model_size
          : "medium",
      whisperDevice:
        typeof whisperPreferences.default_whisper_device === "string" &&
        SUPPORTED_WHISPER_DEVICES.has(whisperPreferences.default_whisper_device)
          ? whisperPreferences.default_whisper_device
          : "auto",
      whisperGpuIndex:
        typeof whisperPreferences.default_whisper_gpu_index === "number" &&
        Number.isInteger(whisperPreferences.default_whisper_gpu_index)
          ? whisperPreferences.default_whisper_gpu_index
          : null,
      aiProvider: updatedUser.default_ai_provider || "openai",
      aiModel: updatedUser.default_ai_model || "",
    });
  } catch (error) {
    console.error("Error updating preferences:", error);
    return NextResponse.json({ error: "Internal server error" }, { status: 500 });
  }
}
