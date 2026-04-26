export const TEXT_TRANSFORM_OPTIONS = ["none", "uppercase", "lowercase", "capitalize"] as const;
export const TEXT_ALIGN_OPTIONS = ["left", "center", "right"] as const;

export type TextTransformOption = (typeof TEXT_TRANSFORM_OPTIONS)[number];
export type TextAlignOption = (typeof TEXT_ALIGN_OPTIONS)[number];

export interface FontStyleOptions {
  fontFamily: string;
  fontSize: number;
  fontColor: string;
  highlightColor: string;
  fontWeight: number;
  lineHeight: number;
  letterSpacing: number;
  textTransform: TextTransformOption;
  textAlign: TextAlignOption;
  strokeColor: string;
  strokeWidth: number;
  strokeBlur: number;
  shadowColor: string;
  shadowOpacity: number;
  shadowBlur: number;
  shadowOffsetX: number;
  shadowOffsetY: number;
  dimUnhighlighted: boolean;
}

export const DEFAULT_FONT_STYLE_OPTIONS: FontStyleOptions = {
  fontFamily: "TikTokSans-Regular",
  fontSize: 24,
  fontColor: "#FFFFFF",
  highlightColor: "#FDE047",
  fontWeight: 600,
  lineHeight: 1.4,
  letterSpacing: 0,
  textTransform: "none",
  textAlign: "center",
  strokeColor: "#000000",
  strokeWidth: 2,
  strokeBlur: 0.6,
  shadowColor: "#000000",
  shadowOpacity: 0.5,
  shadowBlur: 2,
  shadowOffsetX: 0,
  shadowOffsetY: 2,
  dimUnhighlighted: true,
};

const HEX_COLOR_PATTERN = /^#[0-9A-Fa-f]{6}$/;

function clamp(value: number, min: number, max: number): number {
  if (Number.isNaN(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
}

function roundToStep(value: number, step: number): number {
  return Math.round(value / step) * step;
}

function asNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function normalizeInteger(value: unknown, fallback: number, min: number, max: number, step = 1): number {
  const parsed = asNumber(value);
  if (parsed === null) {
    return fallback;
  }
  return clamp(roundToStep(parsed, step), min, max);
}

function normalizeFloat(
  value: unknown,
  fallback: number,
  min: number,
  max: number,
  decimals = 2,
): number {
  const parsed = asNumber(value);
  if (parsed === null) {
    return fallback;
  }
  const clamped = clamp(parsed, min, max);
  const factor = 10 ** decimals;
  return Math.round(clamped * factor) / factor;
}

export function isHexColor(value: unknown): value is string {
  return typeof value === "string" && HEX_COLOR_PATTERN.test(value);
}

export function normalizeHexColor(value: unknown, fallback: string): string {
  return isHexColor(value) ? value.toUpperCase() : fallback;
}

export function isTextTransform(value: unknown): value is TextTransformOption {
  return typeof value === "string" && TEXT_TRANSFORM_OPTIONS.includes(value as TextTransformOption);
}

export function isTextAlign(value: unknown): value is TextAlignOption {
  return typeof value === "string" && TEXT_ALIGN_OPTIONS.includes(value as TextAlignOption);
}

export function normalizeFontSize(size: number): number {
  return normalizeInteger(size, DEFAULT_FONT_STYLE_OPTIONS.fontSize, 24, 48, 1);
}

export function normalizeFontWeight(weight: unknown): number {
  return normalizeInteger(weight, DEFAULT_FONT_STYLE_OPTIONS.fontWeight, 300, 900, 100);
}

export function normalizeLineHeight(value: unknown): number {
  return normalizeFloat(value, DEFAULT_FONT_STYLE_OPTIONS.lineHeight, 1, 2, 1);
}

export function normalizeLetterSpacing(value: unknown): number {
  return normalizeInteger(value, DEFAULT_FONT_STYLE_OPTIONS.letterSpacing, 0, 6, 1);
}

export function normalizeStrokeWidth(value: unknown): number {
  return normalizeInteger(value, DEFAULT_FONT_STYLE_OPTIONS.strokeWidth, 0, 8, 1);
}

export function normalizeStrokeBlur(value: unknown): number {
  return normalizeFloat(value, DEFAULT_FONT_STYLE_OPTIONS.strokeBlur, 0, 4, 1);
}

export function normalizeShadowOpacity(value: unknown): number {
  return normalizeFloat(value, DEFAULT_FONT_STYLE_OPTIONS.shadowOpacity, 0, 1, 2);
}

export function normalizeShadowBlur(value: unknown): number {
  return normalizeInteger(value, DEFAULT_FONT_STYLE_OPTIONS.shadowBlur, 0, 8, 1);
}

export function normalizeShadowOffset(value: unknown): number {
  return normalizeInteger(value, 0, -12, 12, 1);
}

export function normalizeFontStyleOptions(
  raw: Partial<Record<keyof FontStyleOptions, unknown>> | null | undefined,
): FontStyleOptions {
  return {
    fontFamily:
      typeof raw?.fontFamily === "string" && raw.fontFamily.trim().length > 0
        ? raw.fontFamily.trim()
        : DEFAULT_FONT_STYLE_OPTIONS.fontFamily,
    fontSize: normalizeFontSize(asNumber(raw?.fontSize) ?? DEFAULT_FONT_STYLE_OPTIONS.fontSize),
    fontColor: normalizeHexColor(raw?.fontColor, DEFAULT_FONT_STYLE_OPTIONS.fontColor),
    highlightColor: normalizeHexColor(raw?.highlightColor, DEFAULT_FONT_STYLE_OPTIONS.highlightColor),
    fontWeight: normalizeFontWeight(raw?.fontWeight),
    lineHeight: normalizeLineHeight(raw?.lineHeight),
    letterSpacing: normalizeLetterSpacing(raw?.letterSpacing),
    textTransform: isTextTransform(raw?.textTransform) ? raw.textTransform : DEFAULT_FONT_STYLE_OPTIONS.textTransform,
    textAlign: isTextAlign(raw?.textAlign) ? raw.textAlign : DEFAULT_FONT_STYLE_OPTIONS.textAlign,
    strokeColor: normalizeHexColor(raw?.strokeColor, DEFAULT_FONT_STYLE_OPTIONS.strokeColor),
    strokeWidth: normalizeStrokeWidth(raw?.strokeWidth),
    strokeBlur: normalizeStrokeBlur(raw?.strokeBlur),
    shadowColor: normalizeHexColor(raw?.shadowColor, DEFAULT_FONT_STYLE_OPTIONS.shadowColor),
    shadowOpacity: normalizeShadowOpacity(raw?.shadowOpacity),
    shadowBlur: normalizeShadowBlur(raw?.shadowBlur),
    shadowOffsetX: normalizeShadowOffset(raw?.shadowOffsetX),
    shadowOffsetY: normalizeShadowOffset(raw?.shadowOffsetY),
    dimUnhighlighted: typeof raw?.dimUnhighlighted === "boolean" ? raw.dimUnhighlighted : DEFAULT_FONT_STYLE_OPTIONS.dimUnhighlighted,
  };
}
