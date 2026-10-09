// Turns "Name: line" dialogue into movie scenes that alternate between two speakers.

export type Speaker = { name: string; avatarId: string; voiceId: string };
export type PodcastScene = { avatar_id: string; tts_voice_id: string | null; script: string };

export const MAX_SCENES = 30;
const MAX_SCENE_CHARS = 1500;

/** Group speaker turns, splitting long dialogue without dropping its tail. */
export function dialogueToScenes(text: string, speakers: [Speaker, Speaker]): { scenes: PodcastScene[]; ignored: number; overflow: number } {
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
    while (words) {
      const last = scenes[scenes.length - 1];
      if (who === lastSpeaker && last && (last.script + " " + words).length <= MAX_SCENE_CHARS) {
        last.script += " " + words;
        break;
      }
      let end = Math.min(words.length, MAX_SCENE_CHARS);
      if (words.length > end) {
        const boundary = words.lastIndexOf(" ", end);
        if (boundary > 0) end = boundary;
      }
      scenes.push({ avatar_id: speakers[who].avatarId, tts_voice_id: speakers[who].voiceId || null, script: words.slice(0, end) });
      words = words.slice(end).trimStart();
      lastSpeaker = who;
    }
    lastSpeaker = who;
  }
  return { scenes: scenes.slice(0, MAX_SCENES), ignored, overflow: Math.max(0, scenes.length - MAX_SCENES) };
}
