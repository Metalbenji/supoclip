import type { OutputAspectRatio } from "@/app/settings/settings-section-types";

export const OUTPUT_ASPECT_RATIO_OPTIONS: Array<{
  value: OutputAspectRatio;
  label: string;
  description: string;
}> = [
  { value: "auto", label: "Auto", description: "Preserve the source video aspect ratio." },
  { value: "1:1", label: "1:1", description: "Square" },
  { value: "21:9", label: "21:9", description: "Ultrawide" },
  { value: "16:9", label: "16:9", description: "Widescreen" },
  { value: "9:16", label: "9:16", description: "Social story" },
  { value: "4:3", label: "4:3", description: "Classic" },
  { value: "4:5", label: "4:5", description: "Social post" },
  { value: "5:4", label: "5:4", description: "Landscape" },
  { value: "3:4", label: "3:4", description: "Traditional" },
  { value: "3:2", label: "3:2", description: "Standard" },
  { value: "2:3", label: "2:3", description: "Portrait" },
];

export function getOutputAspectRatioLabel(value: OutputAspectRatio): string {
  return OUTPUT_ASPECT_RATIO_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export function getOutputAspectRatioDescription(value: OutputAspectRatio): string {
  return OUTPUT_ASPECT_RATIO_OPTIONS.find((option) => option.value === value)?.description ?? "";
}

export function formatOutputAspectRatioSummary(value: OutputAspectRatio): string {
  const option = OUTPUT_ASPECT_RATIO_OPTIONS.find((entry) => entry.value === value);
  return option ? `${option.label} · ${option.description}` : value;
}
