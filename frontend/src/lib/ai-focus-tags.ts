export const AI_FOCUS_TAG_OPTIONS = [
  { value: "funny", label: "Funny", description: "Bias toward humor, banter, and absurd moments." },
  { value: "clutch", label: "Clutch", description: "Bias toward saves, recoveries, and close wins." },
  { value: "fails", label: "Fails", description: "Bias toward mistakes, whiffs, and entertaining disasters." },
  { value: "hype", label: "Hype", description: "Bias toward high-energy reactions and celebrations." },
  { value: "drama", label: "Drama", description: "Bias toward tension, conflict, and big stakes." },
  { value: "reactions", label: "Reactions", description: "Bias toward memorable emotional responses." },
  { value: "storytelling", label: "Storytelling", description: "Bias toward clips with setup and payoff." },
  { value: "educational", label: "Educational", description: "Bias toward explainers, tips, and insights." },
  { value: "wholesome", label: "Wholesome", description: "Bias toward supportive, heartfelt moments." },
] as const;

export type AiFocusTag = (typeof AI_FOCUS_TAG_OPTIONS)[number]["value"];

const AI_FOCUS_TAG_LABELS = new Map(AI_FOCUS_TAG_OPTIONS.map((option) => [option.value, option.label] as const));

export function formatAiFocusTag(tag: string): string {
  return AI_FOCUS_TAG_LABELS.get(tag as AiFocusTag) ?? tag;
}
