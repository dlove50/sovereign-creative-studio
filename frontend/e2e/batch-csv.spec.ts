import { expect, test } from "@playwright/test";
import { batchRowsFromCsv } from "../src/lib/csv";

test("batch CSV preserves variant IDs and quoted multiline scripts", () => {
  const rows = batchRowsFromCsv('title,script,avatar_id,tts_voice_id\r\n"One, two","Hello\nworld",avatar_a,voice_a\r\nFallback,Hello,,');
  expect(rows).toEqual([
    { title: "One, two", script: "Hello\nworld", avatar_id: "avatar_a", tts_voice_id: "voice_a" },
    { title: "Fallback", script: "Hello" },
  ]);
});

test("legacy headerless CSV still imports title and script", () => {
  expect(batchRowsFromCsv('Greeting,"Say ""hello""."')).toEqual([{ title: "Greeting", script: 'Say "hello".' }]);
});
