/* SCORM 2004 (4th Edition) runtime for Sovereign lessons. Same lesson flow as player.js (SCORM 1.2) with the 2004 API. */
(() => {
  "use strict";
  const lesson = window.SOVEREIGN_LESSON, nodes = lesson.nodes;
  const el = (id) => document.getElementById(id);
  const index = (id) => nodes.findIndex((n) => n.id === id);
  const fresh = () => ({current:index(lesson.start), answers:{}, complete:false});
  let state = fresh(), finished = false;
  const started = Date.now();
  function findAPI(win) {
    for (let tries = 0; win && tries < 10; tries++) {
      try { if (win.API_1484_11) return win.API_1484_11; if (win.parent === win) break; win = win.parent; }
      catch { break; }
    }
    return null;
  }
  let api = findAPI(window);
  if (!api) { try { api = findAPI(window.opener); } catch {} }
  let connected = false;
  try { connected = !!api && String(api.Initialize("")) === "true"; } catch {}
  function restore(raw) {
    try {
      const value = JSON.parse(raw);
      if (!Number.isInteger(value.current) || !nodes[value.current]) return;
      const answers = {};
      for (const [key, answer] of Object.entries(value.answers || {})) {
        if (/^\d+$/.test(key) && nodes[Number(key)]?.question && typeof answer === "boolean") answers[key] = answer;
      }
      state = {current:value.current, answers, complete:value.complete === true && !nodes[value.current].choices.length};
    } catch {}
  }
  if (connected) { try { restore(api.GetValue("cmi.suspend_data")); } catch {} }
  el("title").textContent = lesson.title;
  document.title = lesson.title;
  function save() {
    if (!connected || finished) return;
    try {
      let ok = true;
      const set = (name, value) => { if (String(api.SetValue(name, String(value))) !== "true") ok = false; };
      set("cmi.suspend_data", JSON.stringify(state));
      set("cmi.location", String(state.current));
      set("cmi.completion_status", state.complete ? "completed" : "incomplete");
      const answers = Object.values(state.answers);
      if (answers.length) {
        const percent = Math.round(100 * answers.filter(Boolean).length / answers.length);
        set("cmi.score.min", 0); set("cmi.score.max", 100);
        set("cmi.score.raw", percent); set("cmi.score.scaled", (percent / 100).toFixed(2));
      }
      set("cmi.exit", state.complete ? "normal" : "suspend");
      if (String(api.Commit("")) !== "true") ok = false;
      el("notice").textContent = ok ? "Progress saved to your learning system." : "Your learning system could not save all progress. Keep this lesson open and contact your LMS administrator.";
    } catch { el("notice").textContent = "The learning system is unavailable. Progress may not be saved."; }
  }
  function render() {
    const node = nodes[state.current], video = el("video");
    video.pause(); video.removeAttribute("src"); video.load();
    video.hidden = !node.video_url;
    if (node.video_url) video.src = node.video_url;
    el("heading").textContent = node.title || `Step ${state.current + 1}`;
    el("body").textContent = node.body || "";
    el("question").textContent = node.question || "";
    el("choices").replaceChildren();
    el("feedback").hidden = true; el("continue").hidden = true;
    el("completion").hidden = !state.complete;
    el("completion").textContent = "Lesson completed. You can close this window.";
    for (const choice of node.choices) {
      const button = document.createElement("button"); button.textContent = choice.label;
      button.onclick = () => {
        if (node.question && !Object.prototype.hasOwnProperty.call(state.answers, state.current)) state.answers[state.current] = choice.is_correct === true;
        const next = () => { state.current = index(choice.next); state.complete = false; render(); };
        if (choice.feedback) {
          for (const child of el("choices").children) child.disabled = true;
          el("feedback").textContent = choice.feedback; el("feedback").hidden = false;
          el("continue").hidden = false; el("continue").textContent = "Continue"; el("continue").onclick = next; save();
        } else next();
      };
      el("choices").appendChild(button);
    }
    if (!node.choices.length && !state.complete) {
      el("continue").hidden = false; el("continue").textContent = "Finish lesson";
      el("continue").onclick = () => { state.complete = true; render(); };
    }
    el("step").focus(); save();
  }
  // Reset playback only: LMS first-attempt scoring belongs to the current attempt.
  el("restart").onclick = () => { state.current = index(lesson.start); state.complete = false; render(); };
  if (!connected) el("notice").textContent = "Preview mode. Launch this package in a SCORM 2004 learning system to save progress and scores.";
  window.addEventListener("pagehide", () => {
    if (!connected || finished) return;
    save();
    try {
      const seconds = Math.min(35999999, Math.floor((Date.now() - started) / 1000));
      api.SetValue("cmi.session_time", `PT${Math.floor(seconds / 3600)}H${Math.floor(seconds % 3600 / 60)}M${seconds % 60}S`);
      api.Terminate("");
    } catch {}
    finished = true;
  });
  render();
})();
