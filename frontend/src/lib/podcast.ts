// Turns "Name: line" dialogue into movie scenes that alternate between two speakers.

export type Speaker = { name: string; avatarId: string; voiceId: string };
export type PodcastScene = { avatar_id: string; tts_voice_id: string | null; script: string };

export const MAX_SCENES = 30;
const MAX_SCENE_CHARS = 1500;

/** One scene per run of lines by the same speaker. Lines with no known speaker go to `fallback`. */
export function dialogueToScenes(text: string, speakers: [Speaker, Speaker]): { scenes: PodcastScene[]; ignored: number } {
  const names = speakers.map((s) => s.name.trim().toLowerCase());
  const scenes: PodcastScene[] = [];
  let lastSpeaker = -1;
  let ignored = 0;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const m = line.match(/^([^:]{1,40}):\s*(.+)$/);
    let who = m ? names.indexOf(m[1].trim().toLowerCase()) : -1;
    let words = m && who >= 0 ? m[2].trim() : line;
    if (who < 0) {
      // Continuation of the previous speaker's turn, otherwise the line can't be placed.
      if (lastSpeaker < 0) { ignored++; continue; }
      who = lastSpeaker;
      words = line;
    }
    const last = scenes[scenes.length - 1];
    if (who === lastSpeaker && last && (last.script + " " + words).length <= MAX_SCENE_CHARS) {
      last.script += " " + words;
    } else {
      scenes.push({ avatar_id: speakers[who].avatarId, tts_voice_id: speakers[who].voiceId || null, script: words.slice(0, MAX_SCENE_CHARS) });
    }
    lastSpeaker = who;
  }
  return { scenes: scenes.slice(0, MAX_SCENES), ignored };
}
