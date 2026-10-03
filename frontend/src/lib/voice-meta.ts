import type { VoiceOption } from "@/lib/types";

// Piper does not publish a speaker's gender, so the few bundled voices are labelled by hand.
const GENDER_BY_SPEAKER: Record<string, "Male" | "Female"> = { amy: "Female", lessac: "Female", alan: "Male" };

const isVibeVoice = (v: VoiceOption) => v.id.startsWith("vibevoice:");

/** A voice the user cloned (not one of the voice app's ready-made presets). */
export const isCloneVoice = (v: VoiceOption) => isVibeVoice(v) && v.quality === "clone";

export const cleanVoiceLabel = (v: VoiceOption) => {
  const base = v.label.replace(/\s*\(VibeVoice (clone|preset)\)\s*$/, "");
  // Presets are named like "en-Alice_woman" or "zh-Anchen_man_bgm": show just "Alice".
  return v.quality === "preset" ? base.replace(/^[a-z]{2}-/, "").replace(/_(man|woman)(_bgm)?$/, "").replace(/_/g, " ") : base;
};

export function voiceGender(v: VoiceOption): "Male" | "Female" | null {
  if (v.quality === "preset") {
    if (/_man(_bgm)?$/.test(v.id)) return "Male";
    if (/_woman(_bgm)?$/.test(v.id)) return "Female";
    return null;
  }
  const speaker = v.id.split("-")[1]?.toLowerCase();
  return (speaker && GENDER_BY_SPEAKER[speaker]) || null;
}

const LANGUAGES: Record<string, string> = { en: "English", zh: "Chinese", in: "Indian English", de: "German", fr: "French", es: "Spanish" };
export const voiceLanguage = (v: VoiceOption) => LANGUAGES[v.language.toLowerCase().slice(0, 2)] ?? v.language.toUpperCase();

export function voiceTags(v: VoiceOption): string {
  if (isCloneVoice(v)) return "Cloned voice";
  return [voiceLanguage(v), voiceGender(v), v.quality === "preset" ? "Preset" : v.quality].filter(Boolean).join(" · ");
}
