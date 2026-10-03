import type { AvatarAsset, VoiceOption } from "@/lib/types";

/**
 * The voice an avatar speaks with by default. A look inherits it from its base avatar, and the
 * voice only counts if it is still available (a clone is missing while the voice app is off).
 */
export function defaultVoiceFor(avatar: AvatarAsset | undefined, all: AvatarAsset[], voices: VoiceOption[]): string | null {
  if (!avatar) return null;
  const base = avatar.group_id ? all.find((a) => a.id === avatar.group_id) : undefined;
  const id = avatar.default_voice_id || base?.default_voice_id || null;
  return id && voices.some((v) => v.id === id) ? id : null;
}
