/* xAPI (Tin Can) runtime for Sovereign lessons. The LRS comes from the launch address, as the xAPI launch
   convention defines: ?endpoint=<LRS url>&auth=<Authorization header value>&actor=<actor JSON>. Without them
   the lesson runs in preview mode and sends nothing. */
(() => {
  "use strict";
  const lesson = window.SOVEREIGN_LESSON, nodes = lesson.nodes;
  const el = (id) => document.getElementById(id);
  const index = (id) => nodes.findIndex((n) => n.id === id);
  const fresh = () => ({current:index(lesson.start), answers:{}, complete:false});
  let state = fresh(), finished = false;
  const started = Date.now();
  const params = new URLSearchParams(location.search);
  let actor = null;
  try { actor = JSON.parse(params.get("actor") || ""); } catch {}
  const auth = params.get("auth"), rawEndpoint = params.get("endpoint");
  const connected = !!(rawEndpoint && auth && actor && typeof actor === "object");
  const endpoint = connected ? rawEndpoint.replace(/\/?$/, "/") : "";
  const activityId = lesson.activity_id;
  const VERB = {
    initialized: ["http://adlnet.gov/expapi/verbs/initialized", "initialized"],
    resumed: ["http://adlnet.gov/expapi/verbs/resumed", "resumed"],
    answered: ["http://adlnet.gov/expapi/verbs/answered", "answered"],
    completed: ["http://adlnet.gov/expapi/verbs/completed", "completed"],
    terminated: ["http://adlnet.gov/expapi/verbs/terminated", "terminated"],
  };
  const headers = () => ({"Authorization": auth, "X-Experience-API-Version": "1.0.3", "Content-Type": "application/json"});
  let problem = false;
  function note(text) { el("notice").textContent = text; }
  function send(verb, object, result) {
    if (!connected) return Promise.resolve();
    const statement = {
      actor, verb: {id: VERB[verb][0], display: {"en-US": VERB[verb][1]}},
      object: {objectType: "Activity", id: object.id, definition: {type: "http://adlnet.gov/expapi/activities/" + (object.id === activityId ? "course" : "interaction"), name: {"en-US": object.name}}},
      timestamp: new Date().toISOString(),
    };
    if (result) statement.result = result;
    return fetch(endpoint + "statements", {method: "POST", headers: headers(), body: JSON.stringify(statement), keepalive: true})
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); })
      .catch(() => { problem = true; note("The learning record store did not accept all progress. Keep this lesson open and contact your administrator."); });
  }
  const stateUrl = () => `${endpoint}activities/state?activityId=${encodeURIComponent(activityId)}&agent=${encodeURIComponent(JSON.stringify(actor))}&stateId=progress`;
  const lessonObject = () => ({id: activityId, name: lesson.title});
  const score = () => {
    const answers = Object.values(state.answers);
    if (!answers.length) return null;
    const raw = Math.round(100 * answers.filter(Boolean).length / answers.length);
    return {scaled: raw / 100, raw, min: 0, max: 100};
  };
  const duration = () => {
    const s = Math.min(35999999, Math.floor((Date.now() - started) / 1000));
    return `PT${Math.floor(s / 3600)}H${Math.floor(s % 3600 / 60)}M${s % 60}S`;
  };
  function restore(value) {
    try {
      if (!Number.isInteger(value.current) || !nodes[value.current]) return false;
      const answers = {};
      for (const [key, answer] of Object.entries(value.answers || {})) {
        if (/^\d+$/.test(key) && nodes[Number(key)]?.question && typeof answer === "boolean") answers[key] = answer;
      }
      state = {current: value.current, answers, complete: value.complete === true && !nodes[value.current].choices.length};
      return true;
    } catch { return false; }
  }
  function save() {
    if (!connected || finished) return;
    fetch(stateUrl(), {method: "PUT", headers: headers(), body: JSON.stringify(state), keepalive: true})
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); if (!problem) note("Progress saved to your learning record store."); })
      .catch(() => { problem = true; note("The learning record store could not save your place. Keep this lesson open."); });
  }
  el("title").textContent = lesson.title;
  document.title = lesson.title;
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
        if (node.question && !Object.prototype.hasOwnProperty.call(state.answers, state.current)) {
          state.answers[state.current] = choice.is_correct === true;
          send("answered", {id: `${activityId}/step/${state.current + 1}`, name: node.question}, {response: choice.label, success: choice.is_correct === true});
        }
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
      el("continue").onclick = () => {
        state.complete = true;
        const result = {completion: true, duration: duration()};
        const s = score(); if (s) result.score = s;
        send("completed", lessonObject(), result);
        render();
      };
    }
    el("step").focus(); save();
  }
  el("restart").onclick = () => { state.current = index(lesson.start); state.complete = false; render(); };
  window.addEventListener("pagehide", () => {
    if (!connected || finished) return;
    finished = true;
    send("terminated", lessonObject(), {duration: duration()});
  });
  async function start() {
    if (!connected) { note("Preview mode. Launch this package from an xAPI learning record store to save progress and scores."); render(); return; }
    let resumed = false;
    try {
      const r = await fetch(stateUrl(), {headers: headers()});
      if (r.ok) resumed = restore(await r.json());
    } catch {}
    await send(resumed ? "resumed" : "initialized", lessonObject());
    render();
  }
  start();
})();
