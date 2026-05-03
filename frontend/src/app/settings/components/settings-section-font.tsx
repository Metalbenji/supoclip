import { useId, useEffect, useRef, type ChangeEvent, type CSSProperties } from "react";
import { Palette, Type } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import {
  SUBTITLE_PRESETS,
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
const SCROLL_PREVIEW_WORDS = ["This", "subtitle", "will", "look", "amazing", "right"];

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
   Video Through Text Preview
   Shows a black bar with text cutouts revealing an animated gradient
   (simulating video). JS cycles through words to show karaoke effect.
   ═══════════════════════════════════════════════════════════════════════ */
function VTTPreview({
  previewText,
  previewTextStyle,
  previewTextX,
  previewTextAnchor,
  fontSize,
  dimUnhighlighted,
}: {
  previewText: string;
  previewTextStyle: CSSProperties;
  previewTextX: string;
  previewTextAnchor: "start" | "middle" | "end";
  fontSize: number;
  dimUnhighlighted: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const uid = useId().replace(/:/g, "");
  const gradId = `vtt-grad-${uid}`;
  const wordHoldMs = 700;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // The highlight overlay text element
    const highlightText = container.querySelector<SVGTextElement>("text#vtt-highlight");
    // The base text for getExtentOfChar measurements
    const baseText = container.querySelector<SVGTextElement>("text#vtt-base");
    if (!highlightText || !baseText) return;

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

        // Position highlight text at same baseline
        highlightText.setAttribute("y", String(startExt.y));
        highlightText.setAttribute("dominant-baseline", "auto");

        // Position highlight text using absolute coordinates
        const wordStr = previewText.slice(startChar, endChar);
        highlightText.setAttribute("text-anchor", "start");
        highlightText.setAttribute("x", String(Math.round(startExt.x)));

        highlightText.textContent = wordStr;
        highlightText.setAttribute("fill", `url(#${gradId})`);
        highlightText.setAttribute("opacity", "1");
      } catch {
        highlightText.setAttribute("opacity", "0");
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
  }, [previewText, fontSize, letterSpacing, textTransform, fontFamily, fontWeight, previewTextAnchor, previewTextX, dimUnhighlighted, gradId, wordHoldMs]);

  const svgH = Math.max(70, Math.ceil(fontSize * 1.6));

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height: svgH + 16 }}
    >
      <svg
        className="block w-full overflow-visible"
        width="100%"
        height={svgH}
        role="img"
        aria-label="video through text preview"
      >
        <defs>
          {/* Animated gradient simulating video behind text */}
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#FF6B6B">
              <animate attributeName="stop-color" values="#FF6B6B;#4ECDC4;#45B7D1;#FDE047;#FF6B6B" dur="4s" repeatCount="indefinite" />
            </stop>
            <stop offset="50%" stopColor="#4ECDC4">
              <animate attributeName="stop-color" values="#4ECDC4;#FDE047;#FF6B6B;#45B7D1;#4ECDC4" dur="4s" repeatCount="indefinite" />
            </stop>
            <stop offset="100%" stopColor="#45B7D1">
              <animate attributeName="stop-color" values="#45B7D1;#FF6B6B;#4ECDC4;#FDE047;#45B7D1" dur="4s" repeatCount="indefinite" />
            </stop>
          </linearGradient>
        </defs>
        {/* Black bar background */}
        <rect x="0" y="0" width="100%" height={svgH} fill="#000000" rx="4" />
        {/* Base text layer — dark on black bar, barely visible */}
        <text
          id="vtt-base"
          x={previewTextX}
          y={Math.round(svgH / 2)}
          textAnchor={previewTextAnchor}
          dominantBaseline="central"
          style={previewTextStyle}
          fill={dimUnhighlighted ? "#1a1a1a" : "#555555"}
        >{previewText}</text>
        {/* Highlight overlay — gradient fill positioned by JS */}
        <text
          id="vtt-highlight"
          x={previewTextX}
          y={Math.round(svgH / 2)}
          textAnchor={previewTextAnchor}
          dominantBaseline="central"
          style={previewTextStyle}
          fill={`url(#${gradId})`}
          opacity="0"
        />
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

  // Wheel preview: 4-slot SVG rolls down, clipped to 3 visible rows
  const wheelContainerRef = useRef<HTMLDivElement>(null);
  const wheelSlotH = Math.max(28, Math.ceil(fontSize * lineHeight * 1.1));

  // Hormozi preview: slide highlight box across words
  const hormoziContainerRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (animation !== "vertical_scroll") return;
    const container = wheelContainerRef.current;
    if (!container) return;
    const svg = container.querySelector("svg.wheel-svg") as SVGSVGElement | null;
    if (!svg) return;

    // Select the 4 slot groups
    const slotGroups = container.querySelectorAll<SVGGElement>("g[data-wslot]");
    if (slotGroups.length < 4) return;

    const n = SCROLL_PREVIEW_WORDS.length;
    let idx = 0;
    let cancelled = false;
    const HOLD = 900;
    const SLIDE = 380;
    const slotH = Math.max(28, Math.ceil(fontSize * lineHeight * 1.1));
    const dimOpacity = dimUnhighlighted ? 0.35 : 0.7;

    // Returns [incoming, next, current, prev] for word index i
    function getWords(i: number): string[] {
      return [
        SCROLL_PREVIEW_WORDS[(i + 2) % n],
        SCROLL_PREVIEW_WORDS[(i + 1) % n],
        SCROLL_PREVIEW_WORDS[i],
        SCROLL_PREVIEW_WORDS[(i - 1 + n) % n],
      ];
    }

    function setSlot(slotIdx: number, text: string, highlighted: boolean) {
      const g = slotGroups[slotIdx];
      if (!g) return;
      const texts = g.querySelectorAll<SVGTextElement>("text");
      for (const t of texts) t.textContent = text;
      g.setAttribute("opacity", String(highlighted ? 1 : dimOpacity));
      // Update fill on the last text element (the fill layer)
      const fillText = texts[texts.length - 1];
      if (fillText) fillText.setAttribute("fill", highlighted ? highlightColor : fontColor);
    }

    // Initialize
    const words = getWords(0);
    for (let s = 0; s < 4; s++) setSlot(s, words[s], s === 2);
    svg.style.transition = "none";
    svg.style.transform = `translateY(${-slotH}px)`;

    setTimeout(() => {
      if (cancelled) return;
      function tick() {
        if (cancelled) return;

        // Roll down: slide from -slotH to 0
        svg.style.transition = `transform ${SLIDE}ms cubic-bezier(0.22, 0.61, 0.36, 1)`;
        svg.style.transform = "translateY(0)";

        setTimeout(() => {
          if (cancelled) return;

          // Rotate words and snap back
          idx = (idx + 1) % n;
          const w = getWords(idx);
          for (let s = 0; s < 4; s++) setSlot(s, w[s], s === 2);

          svg.style.transition = "none";
          svg.style.transform = `translateY(${-slotH}px)`;

          setTimeout(() => tick(), HOLD);
        }, SLIDE + 20);
      }
      tick();
    }, 400);

    return () => { cancelled = true; };
  }, [animation, fontSize, lineHeight, dimUnhighlighted, highlightColor, fontColor, wheelSlotH]);

  // Hormozi preview: slide highlight box across words using getExtentOfChar
  useEffect(() => {
    if (animation !== "hormozi") return;
    const container = hormoziContainerRef.current;
    if (!container) return;

    const box = container.querySelector<SVGRectElement>("rect#hormozi-highlight-box");
    const textEl = container.querySelector<SVGTextElement>("text#hormozi-main-text:not([aria-hidden])");
    if (!box || !textEl) return;

    const words = previewText.split(" ").filter(Boolean);
    if (words.length === 0) return;

    let cancelled = false;
    const WORD_HOLD = 700;
    const padX = Math.max(6, fontSize * 0.12);

    // Build char index ranges for each word
    function getWordRanges() {
      const ranges: [number, number][] = [];
      let charIdx = 0;
      for (const word of words) {
        const start = charIdx;
        const end = charIdx + word.length;
        ranges.push([start, end]);
        charIdx = end + 1; // +1 for space
      }
      return ranges;
    }

    function getWordBox(rangeIdx: number) {
      const ranges = getWordRanges();
      if (rangeIdx >= ranges.length) return null;
      const [startChar, endChar] = ranges[rangeIdx];
      try {
        const startExt = textEl.getExtentOfChar(startChar);
        const endExt = textEl.getExtentOfChar(Math.max(startChar, endChar - 1));
        const padY = Math.max(4, fontSize * 0.15);
        const x = startExt.x - padX;
        const w = (endExt.x + endExt.width) - startExt.x + padX * 2;
        const y = startExt.y - padY;
        const h = startExt.height + padY * 2;
        return { x, y, w, h };
      } catch {
        return null;
      }
    }

    let wordIdx = 0;
    function highlightNext() {
      if (cancelled) return;
      const wb = getWordBox(wordIdx % words.length);
      if (wb) {
        box.setAttribute("x", String(wb.x));
        box.setAttribute("y", String(wb.y));
        box.setAttribute("width", String(wb.w));
        box.setAttribute("height", String(wb.h));
        box.setAttribute("opacity", "1");
      }
      wordIdx++;
      setTimeout(() => highlightNext(), WORD_HOLD);
    }

    // Wait for font rendering
    const timer = setTimeout(() => {
      box.setAttribute("opacity", "0");
      highlightNext();
    }, 500);

    return () => { cancelled = true; clearTimeout(timer); };
  }, [animation, previewText, fontSize, letterSpacing, textTransform, fontFamily, fontWeight, previewTextAnchor, previewTextX]);

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
        <Label className="text-sm font-medium text-black">Preview {animation !== "none" ? <span className="text-xs text-gray-400 font-normal">(animated)</span> : null}</Label>
        <div className="p-6 bg-black rounded-lg min-h-[120px] flex items-center overflow-visible">
          <div className="relative w-full">
            {animation === "vertical_scroll" ? (
              /* ═══════════════════════════════════════════════════════════
                 Vertical Scroll preview — 4-slot rolling wheel
                 4 rows in SVG, container clips to 3. SVG translateY
                 rolls down one slot, then snaps back and rotates words.
                 Slot 0 = incoming (hidden), 1 = next, 2 = current, 3 = prev.
                 ═══════════════════════════════════════════════════════════ */
              <div
                ref={wheelContainerRef}
                className="w-full overflow-hidden"
                style={{ height: wheelSlotH * 3 }}
              >
                <svg
                  className="wheel-svg block w-full"
                  width="100%"
                  height={wheelSlotH * 4}
                  role="img"
                  aria-label="wheel preview"
                >
                  <defs>
                    {shadowOpacity > 0 && (
                      <filter id={`${previewShadowFilterId}-wheel`} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                        <feOffset in="SourceAlpha" dx={shadowOffsetX} dy={shadowOffsetY} result="shadow-offset" />
                        <feGaussianBlur in="shadow-offset" stdDeviation={previewShadowStdDeviation} result="shadow-blur" />
                        <feFlood floodColor={shadowColor} floodOpacity={shadowOpacity} result="shadow-color" />
                        <feComposite in="shadow-color" in2="shadow-blur" operator="in" result="shadow-only" />
                      </filter>
                    )}
                    {strokeWidth > 0 && (
                      <filter id={`${previewStrokeFilterId}-wheel`} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                        <feMorphology in="SourceAlpha" operator="dilate" radius={strokeWidth} result="stroke-expanded" />
                        <feComposite in="stroke-expanded" in2="SourceAlpha" operator="out" result="stroke-outer" />
                        <feFlood floodColor={strokeColor} result="stroke-color" />
                        <feComposite in="stroke-color" in2="stroke-outer" operator="in" result="stroke-only" />
                        <feGaussianBlur in="stroke-only" stdDeviation={previewStrokeStdDeviation} result="stroke-final" />
                      </filter>
                    )}
                  </defs>
                  {/* Slot 0: incoming (hidden above viewport) */}
                  <g data-wslot="0" opacity="0.35">
                    {shadowOpacity > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 0.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewShadowFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[2]}</text>
                    )}
                    {strokeWidth > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 0.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewStrokeFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[2]}</text>
                    )}
                    <text x={previewTextX} y={wheelSlotH * 0.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill={fontColor}>{SCROLL_PREVIEW_WORDS[2]}</text>
                  </g>
                  {/* Slot 1: next word (top visible) */}
                  <g data-wslot="1" opacity="0.35">
                    {shadowOpacity > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 1.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewShadowFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[1]}</text>
                    )}
                    {strokeWidth > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 1.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewStrokeFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[1]}</text>
                    )}
                    <text x={previewTextX} y={wheelSlotH * 1.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill={fontColor}>{SCROLL_PREVIEW_WORDS[1]}</text>
                  </g>
                  {/* Slot 2: current word (center, highlighted) */}
                  <g data-wslot="2" opacity="1">
                    {shadowOpacity > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 2.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewShadowFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[0]}</text>
                    )}
                    {strokeWidth > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 2.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewStrokeFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[0]}</text>
                    )}
                    <text x={previewTextX} y={wheelSlotH * 2.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill={highlightColor}>{SCROLL_PREVIEW_WORDS[0]}</text>
                  </g>
                  {/* Slot 3: previous word (bottom visible) */}
                  <g data-wslot="3" opacity="0.35">
                    {shadowOpacity > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 3.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewShadowFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[SCROLL_PREVIEW_WORDS.length - 1]}</text>
                    )}
                    {strokeWidth > 0 && (
                      <text aria-hidden x={previewTextX} y={wheelSlotH * 3.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill="#FFFFFF" filter={`url(#${previewStrokeFilterId}-wheel)`}>{SCROLL_PREVIEW_WORDS[SCROLL_PREVIEW_WORDS.length - 1]}</text>
                    )}
                    <text x={previewTextX} y={wheelSlotH * 3.5} textAnchor={previewTextAnchor} dominantBaseline="middle" style={previewTextStyle} fill={fontColor}>{SCROLL_PREVIEW_WORDS[SCROLL_PREVIEW_WORDS.length - 1]}</text>
                  </g>
                </svg>
              </div>
            ) : animation === "video_through_text" ? (
              /* ═══════════════════════════════════════════════════════════
                 Video Through Text preview — black bar with text cutouts
                 A black bar with an animated gradient behind the text to
                 simulate video bleeding through. JS cycles highlight across
                 words one at a time (karaoke style).
                 ═══════════════════════════════════════════════════════════ */
              <VTTPreview
                previewText={previewText}
                previewTextStyle={previewTextStyle}
                previewTextX={previewTextX}
                previewTextAnchor={previewTextAnchor}
                fontSize={fontSize}
                dimUnhighlighted={dimUnhighlighted}
              />
            ) : animation === "hormozi" ? (
              /* ═══════════════════════════════════════════════════════════
                 Hormozi preview — yellow box behind each word
                 Full text rendered normally. JS measures word positions
                 via getExtentOfChar and sizes/moves a single rect.
                 ═══════════════════════════════════════════════════════════ */
              <div
                ref={hormoziContainerRef}
                className="w-full relative"
                style={{ height: Math.max(70, Math.ceil(fontSize * 1.6)) }}
              >
                <svg
                  className="block w-full overflow-visible"
                  height={Math.max(70, Math.ceil(fontSize * 1.6))}
                  role="img"
                  aria-label="hormozi preview"
                >
                  <defs>
                    {shadowOpacity > 0 && (
                      <filter id={`${previewShadowFilterId}-hormozi`} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                        <feOffset in="SourceAlpha" dx={shadowOffsetX} dy={shadowOffsetY} result="shadow-offset" />
                        <feGaussianBlur in="shadow-offset" stdDeviation={previewShadowStdDeviation} result="shadow-blur" />
                        <feFlood floodColor={shadowColor} floodOpacity={shadowOpacity} result="shadow-color" />
                        <feComposite in="shadow-color" in2="shadow-blur" operator="in" result="shadow-only" />
                      </filter>
                    )}
                    {strokeWidth > 0 && (
                      <filter id={`${previewStrokeFilterId}-hormozi`} x="-50%" y="-50%" width="200%" height="200%" colorInterpolationFilters="sRGB">
                        <feMorphology in="SourceAlpha" operator="dilate" radius={strokeWidth} result="stroke-expanded" />
                        <feComposite in="stroke-expanded" in2="SourceAlpha" operator="out" result="stroke-outer" />
                        <feFlood floodColor={strokeColor} result="stroke-color" />
                        <feComposite in="stroke-color" in2="stroke-outer" operator="in" result="stroke-only" />
                        <feGaussianBlur in="stroke-only" stdDeviation={previewStrokeStdDeviation} result="stroke-final" />
                      </filter>
                    )}
                  </defs>
                  {/* Highlight box — positioned by JS */}
                  <rect
                    id="hormozi-highlight-box"
                    x="0"
                    y="0"
                    width="0"
                    height={fontSize * 1.3}
                    rx={Math.max(4, fontSize * 0.06)}
                    ry={Math.max(4, fontSize * 0.06)}
                    fill={highlightColor}
                    opacity={0}
                    style={{ transition: "all 150ms ease" }}
                  />
                  {shadowOpacity > 0 && (
                    <text
                      aria-hidden
                      x={previewTextX}
                      y={Math.round(Math.max(70, Math.ceil(fontSize * 1.6)) / 2)}
                      textAnchor={previewTextAnchor}
                      dominantBaseline="central"
                      style={previewTextStyle}
                      fill="#FFFFFF"
                      filter={`url(#${previewShadowFilterId}-hormozi)`}
                    >{previewText}</text>
                  )}
                  {strokeWidth > 0 && (
                    <text
                      aria-hidden
                      x={previewTextX}
                      y={Math.round(Math.max(70, Math.ceil(fontSize * 1.6)) / 2)}
                      textAnchor={previewTextAnchor}
                      dominantBaseline="central"
                      style={previewTextStyle}
                      fill="#FFFFFF"
                      filter={`url(#${previewStrokeFilterId}-hormozi)`}
                    >{previewText}</text>
                  )}
                  <text
                    id="hormozi-main-text"
                    x={previewTextX}
                    y={Math.round(Math.max(70, Math.ceil(fontSize * 1.6)) / 2)}
                    textAnchor={previewTextAnchor}
                    dominantBaseline="central"
                    style={previewTextStyle}
                    fill={fontColor}
                  >{previewText}</text>
                </svg>
              </div>
            ) : (
              /* Static preview */
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
            )}
            <style>{`
              @keyframes subtitleScrollIn {
                0% { transform: translateY(-100%); opacity: 0; }
                25% { opacity: 1; }
                100% { transform: translateY(0); opacity: 1; }
              }
              @keyframes scrollRowHighlight {
                0% { transform: translateY(100%); opacity: 0; }
                30% { transform: translateY(0); opacity: 1; }
                100% { transform: translateY(0); opacity: 1; }
              }
              @keyframes wheelRowIn {
                0% { transform: translateY(-40px); opacity: 0; }
                20% { transform: translateY(0); opacity: 1; }
                100% { transform: translateY(0); opacity: 1; }
              }
              @keyframes wheelSpin {
                0% {
                  transform: translateY(-30px);
                  opacity: 0;
                }
                40% {
                  transform: translateY(0);
                  opacity: 1;
                }
                60% {
                  transform: translateY(0);
                  opacity: 1;
                }
                100% {
                  transform: translateY(30px);
                  opacity: 0;
                }
              }
            `}</style>
          </div>
        </div>
      </div>
    </div>
  );
}
