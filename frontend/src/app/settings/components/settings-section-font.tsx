import { useId, type ChangeEvent, type CSSProperties } from "react";
import { Palette, Type } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  SUBTITLE_ANIMATION_OPTIONS,
  SUBTITLE_POSITION_OPTIONS,
  SUBTITLE_PRESETS,
  TEXT_ALIGN_OPTIONS,
  TEXT_TRANSFORM_OPTIONS,
  type SubtitleAnimationOption,
  type SubtitlePresetId,
  type SubtitlePositionOption,
  type TextAlignOption,
  type TextTransformOption,
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
  position: SubtitlePositionOption;
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
  onPositionChange: (value: SubtitlePositionOption) => void;
  onAnimationChange: (value: SubtitleAnimationOption) => void;
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
  onAnimationChange,
  onSubtitlePresetChange,
  onFontUpload,
}: SettingsSectionFontProps) {
  const previewFilterBaseId = useId().replace(/:/g, "");
  const previewStrokeFilterId = `${previewFilterBaseId}-stroke`;
  const previewShadowFilterId = `${previewFilterBaseId}-shadow`;
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
  const previewStrokeStdDeviation = Math.max(0, strokeBlur / 2);
  const previewShadowStdDeviation = Math.max(0, shadowBlur / 2);

  return (
    <div className="space-y-6">
      {/* Style Preset Selector */}
      <div className="space-y-2">
        <Label className="text-sm font-medium text-black flex items-center gap-2">
          <Palette className="w-4 h-4" />
          Style Preset
        </Label>
        <Select
          value={subtitlePreset}
          onValueChange={(value) => onSubtitlePresetChange(value as SubtitlePresetId)}
          disabled={isSaving || isUploadingFont}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select preset" />
          </SelectTrigger>
          <SelectContent>
            {SUBTITLE_PRESETS.map((preset) => (
              <SelectItem key={preset.id} value={preset.id}>
                {preset.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(() => {
          const activePreset = SUBTITLE_PRESETS.find((p) => p.id === subtitlePreset);
          return activePreset ? (
            <p className="text-xs text-gray-500">{activePreset.description}</p>
          ) : null;
        })()}
      </div>

      {/* Position and Animation */}
      <div className="grid gap-4 sm:grid-cols-2 pt-1">
        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Position</Label>
          <Select
            value={position}
            onValueChange={(value) => onPositionChange(value as SubtitlePositionOption)}
            disabled={isSaving || isUploadingFont}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select position" />
            </SelectTrigger>
            <SelectContent>
              {SUBTITLE_POSITION_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option.charAt(0).toUpperCase() + option.slice(1).replace("_", " ")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label className="text-sm font-medium text-black">Animation</Label>
          <Select
            value={animation}
            onValueChange={(value) => onAnimationChange(value as SubtitleAnimationOption)}
            disabled={isSaving || isUploadingFont}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Select animation" />
            </SelectTrigger>
            <SelectContent>
              {SUBTITLE_ANIMATION_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option === "none" ? "None" : "Vertical Scroll"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
            max={48}
            min={24}
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
        <Label className="text-sm font-medium text-black flex items-center gap-2">
          <Palette className="w-4 h-4" />
          Font Color
        </Label>
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
        <div className="p-6 bg-black rounded-lg min-h-[120px] flex items-center">
          <div className="relative w-full">
            <svg
              className="block w-full overflow-visible"
              height={previewSvgHeight}
              role="img"
              aria-label={previewText}
            >
              <defs>
                {shadowOpacity > 0 && (
                  <filter id={previewShadowFilterId} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                    <feOffset in="SourceAlpha" dx={shadowOffsetX} dy={shadowOffsetY} result="shadow-offset" />
                    <feGaussianBlur in="shadow-offset" stdDeviation={previewShadowStdDeviation} result="shadow-blur" />
                    <feFlood floodColor={shadowColor} floodOpacity={shadowOpacity} result="shadow-color" />
                    <feComposite in="shadow-color" in2="shadow-blur" operator="in" result="shadow-only" />
                  </filter>
                )}
                {strokeWidth > 0 && (
                  <filter id={previewStrokeFilterId} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                    <feMorphology in="SourceAlpha" operator="dilate" radius={strokeWidth} result="stroke-expanded" />
                    <feComposite in="stroke-expanded" in2="SourceAlpha" operator="out" result="stroke-outer" />
                    <feFlood floodColor={strokeColor} result="stroke-color" />
                    <feComposite in="stroke-color" in2="stroke-outer" operator="in" result="stroke-only" />
                    <feGaussianBlur in="stroke-only" stdDeviation={previewStrokeStdDeviation} result="stroke-final" />
                  </filter>
                )}
              </defs>

              {shadowOpacity > 0 && (
                <text
                  aria-hidden
                  x={previewTextX}
                  y="50%"
                  textAnchor={previewTextAnchor}
                  dominantBaseline="middle"
                  style={previewTextStyle}
                  fill="#FFFFFF"
                  filter={`url(#${previewShadowFilterId})`}
                >
                  {previewText}
                </text>
              )}

              {strokeWidth > 0 && (
                <text
                  aria-hidden
                  x={previewTextX}
                  y="50%"
                  textAnchor={previewTextAnchor}
                  dominantBaseline="middle"
                  style={previewTextStyle}
                  fill="#FFFFFF"
                  filter={`url(#${previewStrokeFilterId})`}
                >
                  {previewText}
                </text>
              )}

              <text
                x={previewTextX}
                y="50%"
                textAnchor={previewTextAnchor}
                dominantBaseline="middle"
                style={previewTextStyle}
                fill={fontColor}
              >
                {previewText}
              </text>
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}
