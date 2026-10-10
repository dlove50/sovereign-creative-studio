export const MOTION_STORAGE_KEY = "scs_motion_preference";

export type MotionPreference = "system" | "on" | "off";

const VALID_MOTION_PREFERENCES = new Set<MotionPreference>(["system", "on", "off"]);

export function parseMotionPreference(value: string | null | undefined): MotionPreference {
  return value && VALID_MOTION_PREFERENCES.has(value as MotionPreference)
    ? (value as MotionPreference)
    : "system";
}

export function resolveMotionEnabled(
  preference: MotionPreference,
  systemReduced: boolean,
): boolean {
  if (preference === "on") return true;
  if (preference === "off") return false;
  return !systemReduced;
}
