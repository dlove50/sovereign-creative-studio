import type { VoiceOption } from "@/lib/types";

// Piper does not publish a speaker's gender, so the few bundled voices are labelled by hand.
const GENDER_BY_SPEAKER: Record<string, "Male" | "Female"> = { amy: "Female", lessac: "Female", alan: "Male" };

export const isCloneVoice = (v: VoiceOption) => v.id.startsWith("vibevoice:");

export const cleanVoiceLabel = (v: VoiceOption) => v.label.replace(/\s*\(VibeVoice clone\)\s*$/, "");

export function voiceGender(v: VoiceOption): "Male" | "Female" | null {
  const speaker = v.id.split("-")[1]?.toLowerCase();
  return (speaker && GENDER_BY_SPEAKER[speaker]) || null;
}

const LANGUAGES: Record<string, string> = { en: "English", zh: "Chinese", in: "Indian English", de: "German", fr: "French", es: "Spanish" };
export const voiceLanguage = (v: VoiceOption) => LANGUAGES[v.language.toLowerCase().slice(0, 2)] ?? v.language.toUpperCase();

export function voiceTags(v: VoiceOption): string {
  if (isCloneVoice(v)) return "Cloned voice";
  return [voiceLanguage(v), voiceGender(v), v.quality].filter(Boolean).join(" · ");
}
