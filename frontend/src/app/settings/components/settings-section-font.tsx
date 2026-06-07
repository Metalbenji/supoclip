import { useId, useEffect, useRef, type ChangeEvent, type CSSProperties } from "react";
import { Type } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  TEXT_ALIGN_OPTIONS,
  TEXT_TRANSFORM_OPTIONS,
  type SubtitlePresetId,
  type TextAlignOption,
  type TextTransformOption,
  type SubtitleAnimationOption,
} from "@/lib/font-style-options";

interface SettingsSectionFontProps {
  isSaving: boolean;
  availableFonts: Array<{ name: string; display_name: string }>;
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
  position: number;
  animation: SubtitleAnimationOption;
  subtitlePreset: SubtitlePresetId;
  isUploadingFont: boolean;
  fontUploadMessage: string | null;
  fontUploadError: string | null;
  onFontFamilyChange: (value: string) => void;
  onFontSizeChange: (size: number) => void;
  onFontColorChange: (color: string) => void;
  onHighlightColorChange: (color: string) => void;
  onFontWeightChange: (weight: number) => void;
  onLineHeightChange: (lineHeight: number) => void;
  onLetterSpacingChange: (spacing: number) => void;
  onTextTransformChange: (transform: TextTransformOption) => void;
  onTextAlignChange: (align: TextAlignOption) => void;
  onStrokeColorChange: (color: string) => void;
  onStrokeWidthChange: (width: number) => void;
  onStrokeBlurChange: (blur: number) => void;
  onShadowColorChange: (color: string) => void;
  onShadowOpacityChange: (opacity: number) => void;
  onShadowBlurChange: (blur: number) => void;
  onShadowOffsetXChange: (offset: number) => void;
  onShadowOffsetYChange: (offset: number) => void;
  onDimUnhighlightedChange: (value: boolean) => void;
  onPositionChange: (value: number) => void;
  onSubtitlePresetChange: (presetId: SubtitlePresetId) => void;
  onFontUpload: (event: ChangeEvent<HTMLInputElement>) => void;
}

const SWATCH_COLORS = ["#FFFFFF", "#000000", "#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1"];
const PREVIEW_TEXT = "Your subtitle will look like this";

function applyTextTransform(text: string, mode: TextTransformOption): string {
  if (mode === "uppercase") {
    return text.toUpperCase();
  }
  if (mode === "lowercase") {
    return text.toLowerCase();
  }
  if (mode === "capitalize") {
    return text.replace(/\b\p{L}/gu, (match) => match.toUpperCase());
  }
  return text;
}

function formatTextOption(option: string): string {
  return option.charAt(0).toUpperCase() + option.slice(1);
}

/* ═══════════════════════════════════════════════════════════════════════
   Karaoke Preview — word-by-word highlight for Classic / Minimal
   Renders base text in fontColor, then JS cycles through each word
   overlaying it in highlightColor using getExtentOfChar. When
   dimUnhighlighted is on, un-highlighted words dim to ~35% opacity.
   ═══════════════════════════════════════════════════════════════════════ */
function KaraokePreview({
  previewText,
  previewTextStyle,
  previewTextX,
  previewTextAnchor,
  fontSize,
  highlightColor,
  fontColor,
  dimUnhighlighted,
  letterSpacing,
  textTransform,
  fontFamily,
  fontWeight,
  strokeColor,
  strokeWidth,
}: {
  previewText: string;
  previewTextStyle: CSSProperties;
  previewTextX: string;
  previewTextAnchor: "start" | "middle" | "end";
  fontSize: number;
  highlightColor: string;
  fontColor: string;
  dimUnhighlighted: boolean;
  letterSpacing: number;
  textTransform: string;
  fontFamily: string;
  fontWeight: number;
  strokeColor: string;
  strokeWidth: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wordHoldMs = 700;
  const previewSvgHeight = Math.max(70, Math.ceil(fontSize * 1.6));
  const uid = useId().replace(/:/g, "");

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Base text for getExtentOfChar measurements
    const baseText = container.querySelector<SVGTextElement>("text#karaoke-base");
    // Clip rect that reveals only the current word on the highlight overlay
    const clipRect = container.querySelector<SVGRectElement>("rect#karaoke-clip-rect");

    if (!baseText || !clipRect) return;

    const words = previewText.split(" ").filter(Boolean);
    if (words.length === 0) return;

    let cancelled = false;
    let wordIdx = 0;

    function getWordRanges(): [number, number][] {
      const ranges: [number, number][] = [];
      let charIdx = 0;
      for (const word of words) {
        ranges.push([charIdx, charIdx + word.length]);
        charIdx += word.length + 1;
      }
      return ranges;
    }

    function showWord(idx: number) {
      const ranges = getWordRanges();
      if (idx >= ranges.length) return;
      const [startChar, endChar] = ranges[idx];

      try {
        const startExt = baseText.getExtentOfChar(startChar);
        const endExt = baseText.getExtentOfChar(Math.max(startChar, endChar - 1));

        // Position clip rect over the current word
        clipRect.setAttribute("x", String(Math.round(startExt.x)));
        clipRect.setAttribute("y", String(Math.round(startExt.y - 4)));
        clipRect.setAttribute("width", String(Math.round(endExt.x + endExt.width - startExt.x + 4)));
        clipRect.setAttribute("height", String(Math.round(startExt.height + 8)));
      } catch {
        clipRect.setAttribute("width", "0");
      }
    }

    const timer = setTimeout(() => {
      showWord(0);
      wordIdx = 1;
      function tick() {
        if (cancelled) return;
        showWord(wordIdx % words.length);
        wordIdx++;
        setTimeout(() => tick(), wordHoldMs);
      }
      tick();
    }, 500);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    previewText, fontSize, letterSpacing, textTransform, fontFamily, fontWeight,
    previewTextAnchor, previewTextX, dimUnhighlighted, highlightColor,
    strokeWidth, wordHoldMs,
  ]);

  return (
    <div ref={containerRef} className="w-full overflow-visible" style={{ height: previewSvgHeight + 16 }}>
      <svg
        className="block w-full overflow-visible"
        width="100%"
        height={previewSvgHeight}
        role="img"
        aria-label="karaoke preview"
      >
        <defs>
          <clipPath id={`karaoke-clip-${uid}`}>
            <rect id="karaoke-clip-rect" x="0" y="0" width="0" height={previewSvgHeight} />
          </clipPath>
        </defs>

        {/* Stroke layer: fill=none so only the outline shows */}
        {strokeWidth > 0 && (
          <text
            aria-hidden
            x={previewTextX}
            y="50%"
            textAnchor={previewTextAnchor}
            dominantBaseline="middle"
            style={previewTextStyle}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth * 2}
          >{previewText}</text>
        )}

        {/* Base text: solid fill in fontColor, dimmed via opacity when dimUnhighlighted */}
        <text
          id="karaoke-base"
          x={previewTextX}
          y="50%"
          textAnchor={previewTextAnchor}
          dominantBaseline="middle"
          style={previewTextStyle}
          fill={fontColor}
          opacity={dimUnhighlighted ? "0.35" : "1"}
        >{previewText}</text>

        {/* Stroke layer for highlight: clipped same as highlight fill */}
        {strokeWidth > 0 && (
          <text
            aria-hidden
            x={previewTextX}
            y="50%"
            textAnchor={previewTextAnchor}
            dominantBaseline="middle"
            style={previewTextStyle}
            fill="none"
            stroke={strokeColor}
            strokeWidth={strokeWidth * 2}
            clipPath={`url(#karaoke-clip-${uid})`}
          >{previewText}</text>
        )}

        {/* Highlighted word — solid fill at full opacity, clipped to current word only */}
        <text
          id="karaoke-highlight"
          x={previewTextX}
          y="50%"
          textAnchor={previewTextAnchor}
          dominantBaseline="middle"
          style={previewTextStyle}
          fill={highlightColor}
          clipPath={`url(#karaoke-clip-${uid})`}
        >{previewText}</text>
      </svg>
    </div>
  );
}

export function SettingsSectionFont({
  isSaving,
  availableFonts,
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
  dimUnhighlighted,
  position,
  animation,
  subtitlePreset,
  isUploadingFont,
  fontUploadMessage,
  fontUploadError,
  onFontFamilyChange,
  onFontSizeChange,
  onFontColorChange,
  onHighlightColorChange,
  onFontWeightChange,
  onLineHeightChange,
  onLetterSpacingChange,
  onTextTransformChange,
  onTextAlignChange,
  onStrokeColorChange,
  onStrokeWidthChange,
  onStrokeBlurChange,
  onShadowColorChange,
  onShadowOpacityChange,
  onShadowBlurChange,
  onShadowOffsetXChange,
  onShadowOffsetYChange,
  onDimUnhighlightedChange,
  onPositionChange,
  onSubtitlePresetChange,
  onFontUpload,
}: SettingsSectionFontProps) {
  const previewText = applyTextTransform(PREVIEW_TEXT, textTransform);
  const previewTextAnchor: "start" | "middle" | "end" =
    textAlign === "left" ? "start" : textAlign === "right" ? "end" : "middle";
  const previewTextX = textAlign === "left" ? "4%" : textAlign === "right" ? "96%" : "50%";
  const previewTextStyle: CSSProperties = {
    fontSize: `${fontSize}px`,
    fontFamily: `'${fontFamily}', system-ui, -apple-system, sans-serif`,
    fontWeight,
    letterSpacing: `${letterSpacing}px`,
  };
  const previewSvgHeight = Math.max(70, Math.ceil(fontSize * lineHeight * 2.2));

  return (
    <div className="space-y-6">
      {/* Position slider */}
      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Position: {position}%</Label>
        <div className="px-2 pt-5">
          <Slider
            value={[position]}
            onValueChange={(value) => onPositionChange(value[0])}
            min={10}
            max={90}
            step={1}
            disabled={isSaving || isUploadingFont}
            className="w-full"
          />
        </div>
        <p className="text-xs text-gray-500">
          {position <= 25 ? "Top" : position <= 60 ? "Center" : "Bottom"} — vertical placement of subtitles
        </p>
      </div>

      {/* Font Family */}
      <div className="space-y-2">
        <Label className="text-sm font-medium text-black flex items-center gap-2">
          <Type className="w-4 h-4" />
          Font Family
        </Label>
        <Select value={fontFamily} onValueChange={onFontFamilyChange} disabled={isSaving || isUploadingFont}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select font" />
          </SelectTrigger>
          <SelectContent>
            {availableFonts.map((font) => (
              <SelectItem key={font.name} value={font.name}>
                {font.display_name}
              </SelectItem>
            ))}
            {availableFonts.length === 0 && <SelectItem value="TikTokSans-Regular">TikTok Sans Regular</SelectItem>}
          </SelectContent>
        </Select>
        <input
          type="file"
          accept=".ttf,font/ttf"
          onChange={onFontUpload}
          disabled={isSaving || isUploadingFont}
          className="file:text-foreground placeholder:text-muted-foreground selection:bg-primary selection:text-primary-foreground dark:bg-input/30 border-input flex h-9 w-full min-w-0 rounded-md border bg-transparent px-3 py-1 text-sm shadow-xs transition-[color,box-shadow] outline-none file:inline-flex file:h-7 file:border-0 file:bg-transparent file:text-sm file:font-medium disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive"
        />
        <p className="text-xs text-gray-500">
          {isUploadingFont ? "Uploading font..." : "Upload a .ttf file to add it to this list."}
        </p>
        {fontUploadMessage && <p className="text-xs text-green-600">{fontUploadMessage}</p>}
        {fontUploadError && <p className="text-xs text-red-600">{fontUploadError}</p>}
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Font Size: {fontSize}px</Label>
        <div className="px-2 pt-5">
          <Slider
            value={[fontSize]}
            onValueChange={(value) => onFontSizeChange(value[0])}
            max={128}
            min={12}
            step={1}
            disabled={isSaving || isUploadingFont}
            className="w-full"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Font Weight: {fontWeight}</Label>
        <div className="px-2 pt-5">
          <Slider
            value={[fontWeight]}
            onValueChange={(value) => onFontWeightChange(value[0])}
            max={900}
            min={300}
            step={100}
            disabled={isSaving || isUploadingFont}
            className="w-full"
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Line Height: {lineHeight.toFixed(1)}</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[lineHeight]}
              onValueChange={(value) => onLineHeightChange(value[0])}
              min={1}
              max={2}
              step={0.1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Letter Spacing: {letterSpacing}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[letterSpacing]}
              onValueChange={(value) => onLetterSpacingChange(value[0])}
              min={0}
              max={6}
              step={1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Text Transform</Label>
          <Select
            value={textTransform}
            onValueChange={(value) => onTextTransformChange(value as TextTransformOption)}
            disabled={isSaving || isUploadingFont}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select transform" />
            </SelectTrigger>
            <SelectContent>
              {TEXT_TRANSFORM_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {formatTextOption(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Text Align</Label>
          <Select
            value={textAlign}
            onValueChange={(value) => onTextAlignChange(value as TextAlignOption)}
            disabled={isSaving || isUploadingFont}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select alignment" />
            </SelectTrigger>
            <SelectContent>
              {TEXT_ALIGN_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {formatTextOption(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Font Color</Label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={fontColor}
            onChange={(event) => onFontColorChange(event.target.value)}
            disabled={isSaving || isUploadingFont}
            className="w-12 h-10 rounded border border-gray-300 cursor-pointer disabled:cursor-not-allowed"
          />
          <Input
            type="text"
            value={fontColor}
            onChange={(event) => onFontColorChange(event.target.value)}
            disabled={isSaving || isUploadingFont}
            placeholder="#FFFFFF"
            className="flex-1 h-10"
            pattern="^#[0-9A-Fa-f]{6}$"
          />
        </div>
        <div className="flex gap-2 mt-2">
          {SWATCH_COLORS.map((color) => (
            <button
              key={color}
              type="button"
              onClick={() => onFontColorChange(color)}
              disabled={isSaving || isUploadingFont}
              className="w-8 h-8 rounded border-2 border-gray-300 cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
              style={{ backgroundColor: color }}
              title={color}
            />
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Highlight Color</Label>
        <div className="flex items-center gap-2">
          <input
            type="color"
            value={highlightColor}
            onChange={(event) => onHighlightColorChange(event.target.value)}
            disabled={isSaving || isUploadingFont}
            className="w-12 h-10 rounded border border-gray-300 cursor-pointer disabled:cursor-not-allowed"
          />
          <Input
            type="text"
            value={highlightColor}
            onChange={(event) => onHighlightColorChange(event.target.value)}
            disabled={isSaving || isUploadingFont}
            placeholder="#FDE047"
            className="flex-1 h-10"
            pattern="^#[0-9A-Fa-f]{6}$"
          />
        </div>
        <div className="flex gap-2 mt-2">
          {SWATCH_COLORS.map((color) => (
            <button
              key={`highlight-${color}`}
              type="button"
              onClick={() => onHighlightColorChange(color)}
              disabled={isSaving || isUploadingFont}
              className="w-8 h-8 rounded border-2 border-gray-300 cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
              style={{ backgroundColor: color }}
              title={color}
            />
          ))}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Stroke Color</Label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={strokeColor}
              onChange={(event) => onStrokeColorChange(event.target.value)}
              disabled={isSaving || isUploadingFont}
              className="w-12 h-10 rounded border border-gray-300 cursor-pointer disabled:cursor-not-allowed"
            />
            <Input
              type="text"
              value={strokeColor}
              onChange={(event) => onStrokeColorChange(event.target.value)}
              disabled={isSaving || isUploadingFont}
              placeholder="#000000"
              className="flex-1 h-10"
            pattern="^#[0-9A-Fa-f]{6}$"
            />
          </div>
          <div className="flex gap-2 mt-2">
            {SWATCH_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => onStrokeColorChange(color)}
                disabled={isSaving || isUploadingFont}
                className="w-8 h-8 rounded border-2 border-gray-300 cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
                style={{ backgroundColor: color }}
                title={color}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Stroke Width: {strokeWidth}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[strokeWidth]}
              onValueChange={(value) => onStrokeWidthChange(value[0])}
              min={0}
              max={8}
              step={1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Stroke Blur: {strokeBlur.toFixed(1)}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[strokeBlur]}
              onValueChange={(value) => onStrokeBlurChange(value[0])}
              min={0}
              max={4}
              step={0.1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Shadow Color</Label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={shadowColor}
              onChange={(event) => onShadowColorChange(event.target.value)}
              disabled={isSaving || isUploadingFont}
              className="w-12 h-10 rounded border border-gray-300 cursor-pointer disabled:cursor-not-allowed"
            />
            <Input
              type="text"
              value={shadowColor}
              onChange={(event) => onShadowColorChange(event.target.value)}
              disabled={isSaving || isUploadingFont}
              placeholder="#000000"
              className="flex-1 h-10"
            pattern="^#[0-9A-Fa-f]{6}$"
            />
          </div>
          <div className="flex gap-2 mt-2">
            {SWATCH_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => onShadowColorChange(color)}
                disabled={isSaving || isUploadingFont}
                className="w-8 h-8 rounded border-2 border-gray-300 cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
                style={{ backgroundColor: color }}
                title={color}
              />
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">
            Shadow Opacity: {Math.round(shadowOpacity * 100)}%
          </Label>
          <div className="px-2 pt-5">
            <Slider
              value={[shadowOpacity]}
              onValueChange={(value) => onShadowOpacityChange(value[0])}
              min={0}
              max={1}
              step={0.05}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Shadow Blur: {shadowBlur}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[shadowBlur]}
              onValueChange={(value) => onShadowBlurChange(value[0])}
              min={0}
              max={8}
              step={1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Shadow X: {shadowOffsetX}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[shadowOffsetX]}
              onValueChange={(value) => onShadowOffsetXChange(value[0])}
              min={-12}
              max={12}
              step={1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Shadow Y: {shadowOffsetY}px</Label>
          <div className="px-2 pt-5">
            <Slider
              value={[shadowOffsetY]}
              onValueChange={(value) => onShadowOffsetYChange(value[0])}
              min={-12}
              max={12}
              step={1}
              disabled={isSaving || isUploadingFont}
              className="w-full"
            />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between rounded-lg border border-gray-200 p-4">
        <div className="space-y-0.5">
          <Label className="text-sm font-medium text-black">Dim Unhighlighted Words</Label>
          <p className="text-xs text-gray-500">
            When enabled, words not yet spoken are shown at reduced opacity for a karaoke effect.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={dimUnhighlighted}
          onClick={() => onDimUnhighlightedChange(!dimUnhighlighted)}
          disabled={isSaving || isUploadingFont}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${
            dimUnhighlighted ? "bg-black" : "bg-gray-300"
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
              dimUnhighlighted ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      <div className="space-y-2">
        <Label className="text-sm font-medium text-black">Preview</Label>
        <div className="p-6 bg-black rounded-lg min-h-[120px] flex items-center overflow-visible">
          <div className="relative w-full">
            <KaraokePreview
              previewText={previewText}
              previewTextStyle={previewTextStyle}
              previewTextX={previewTextX}
              previewTextAnchor={previewTextAnchor}
              fontSize={fontSize}
              highlightColor={highlightColor}
              fontColor={fontColor}
              dimUnhighlighted={dimUnhighlighted}
              letterSpacing={letterSpacing}
              textTransform={textTransform}
              fontFamily={fontFamily}
              fontWeight={fontWeight}
              strokeColor={strokeColor}
              strokeWidth={strokeWidth}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
