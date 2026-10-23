# Cloud escalation and the reference loop

Design note. Written 2026-10-23 for David, against the code as it stands on
`origin/amd-sync` (`39a399e`) and `origin/master` (`9e2ebd2`).

David's ask, in their words: keep the majority of the work local on the R9700,
but use the Claude / OpenAI / HeyGen accounts when the hardware cannot produce
the quality needed — and have the local side learn from those results so it
closes the gap over time.

Most of the first half already exists. The second half needs a correction
before it can be built. Both are below.

---

## 1. What is already built

Nothing here needs writing. It is on `amd-sync`, unmerged.

| Piece | Where | What it does |
|---|---|---|
| Provider registry | `backend/app/services/integrations.py` | Five providers configured: `fal`, `heygen`, `elevenlabs`, `seedance`, `openai`. Keys live in `SECRETS_DIR`, masked in the UI, never served to the browser, excluded from backups, gitignored. |
| Cloud job runner | `backend/app/services/cloud_media.py` (371 lines) | Calls HeyGen and ElevenLabs. Local idempotency key per request; remote job IDs persisted *before* polling, so an interrupted submit is never replayed against an unknown billing outcome. |
| Cloud API surface | `backend/app/routers/cloud_media.py` | `/api/cloud`, admin-only. Eleven operations including `avatar-video`, `tts`, `dubbing`, `voice-clone`, `music`. |
| Spend consent | same router | Every request carries `accept_charges: Literal[True]`. The type makes it unskippable — a request without it fails validation, it cannot be defaulted. |
| Image escalation hook | `backend/app/generators/__init__.py` (on `master` already) | `get_generator(provider=...)` routes `openai_image_api` to the cloud and anything else to local ComfyUI. The seam exists. |
| Prompt rewriting | `backend/app/services/prompt_assist.py` | `clean` and `write` over a local Ollama model. Already improves prompts; currently local-only. |

So: **the accounts are wired, the keys are stored safely, and the spend
consent is already strict.** What is missing is narrower than it looks.

## 2. What is deliberately absent

The first line of `cloud_media.py` is a design decision, not an oversight:

> Official cloud APIs; no model extraction, automatic retries or paid fallbacks.

Two of the three exclusions are exactly what David is now asking for. That is
fine — it is their system and their money — but it should be a decision taken
knowingly rather than a line quietly deleted. The reasons behind it are good
ones, and the design below keeps them satisfied by other means:

- **No paid fallbacks** guards against a failing local job silently becoming a
  bill. A crash loop that escalates on every retry is how a credit balance
  disappears overnight.
- **No model extraction** guards against the thing section 4 explains cannot
  work anyway, and which provider terms generally forbid.

## 3. What to add: the escalation policy

A new module, `backend/app/services/escalation.py`. It decides; it never calls a
provider itself. Keeping the decision pure makes it testable without a network.

```python
@dataclass(frozen=True)
class Decision:
    escalate: bool
    provider: str | None       # "heygen" | "openai" | None
    reason: str                # shown to the user, logged verbatim
    needs_consent: bool        # True -> surface a confirm, do not spend yet
    estimated_cost: str | None # provider's own units, never invented

def decide(*, job_kind: str, failure: str | None, policy: str,
           spend_state: SpendState) -> Decision: ...
```

### The policy setting

`ESCALATION_POLICY` in config, four values, defaulting to the most conservative:

| Value | Behaviour |
|---|---|
| `off` | Never escalate. Local only. **Default.** |
| `ask` | On local failure, offer cloud and wait for consent. Nothing spends unattended. |
| `on_failure` | Escalate automatically when local *fails* — OOM, GPU wedged, timeout. Quality-based escalation still asks. |
| `auto` | Escalate on failure and on a quality verdict. Highest spend risk. |

David's description — "if my hardware cannot produce it" for failures, "if I
need professional graphics" for quality — maps to `on_failure`. That is the
recommended setting once the guards below are in place, not before.

### Guards, which apply at every policy level

These are the reason `on_failure` is safe to switch on at all.

1. **One escalation per job, ever.** Keyed on the job id, persisted. A retry
   loop cannot bill twice for the same piece of work. This is the single most
   important guard.
2. **Daily and per-job spend ceilings**, counted in the provider's own units,
   refused at the ceiling rather than queued.
3. **Failures that must never escalate.** A bad prompt, a missing model file, a
   malformed workflow, a 4xx from the local engine — these fail the same way on
   the cloud, so paying for them buys nothing. Only genuine capability and
   capacity failures escalate: OOM, SVM wedge, timeout, out-of-VRAM.
4. **Escalation is recorded as a distinct ledger entry.** The existing credit
   ledger counts local generations. Cloud spend is real money and must not be
   mixed into the same number — a separate transaction type, so "what did this
   month cost" is answerable.
5. **A kill switch that is one env var**, so a runaway can be stopped without a
   deploy.

### Which service for which job

Worth stating plainly, because the ask conflated a few things:

| Need | Goes to | Note |
|---|---|---|
| Talking avatar, presenter video | **HeyGen** | Already wired. This is its actual specialism. |
| Professional still images | **OpenAI** (`gpt-image-1`) | `openai_image_api` seam already exists. |
| Voice, dubbing, cloning | **ElevenLabs** | Already wired. |
| Copy, scripts, prompt rewriting | **Claude** (incl. Haiku) | Already a `COPY_BACKEND` option. |

**Claude Code and Codex do not belong in this table.** They are coding agents —
they write and change the software itself. They cannot render a frame or
produce a graphic, and no amount of wiring will make them do so. The Claude
*models* are the right tool for words and for prompt-writing, and Haiku is a
good fit there because it is fast and cheap. For pictures and video the paths
are HeyGen and OpenAI.

## 4. What "learn from it" can and cannot mean

This part of the ask needs a straight answer.

**Cannot be done.** The local R9700 cannot learn how HeyGen or OpenAI produce
their results by calling their APIs. An API returns a finished picture or video
and nothing else — no weights, no architecture, no training data, no
intermediate steps. Watching a rendered output teaches a local model nothing
about the model that made it, in the way that watching a film teaches you
nothing about the camera's firmware. Training a local model on collected cloud
outputs is a real technique in the research literature, but it needs a
dataset at a scale this hardware cannot train on, it degrades rather than
matches the source, and provider terms generally prohibit using outputs to
build a competing model. It is not a route to the quality being chased.

**Can be done, and genuinely helps.** The gap between a local render and a
professional one is usually not the model's weights — it is the prompt, the
sampler settings, the resolution ladder, the refiner pass, and the LoRA
stack. Those are all things the system can carry over, and all things that
live in the workflow JSON rather than in the weights. Three concrete loops:

1. **Reference capture.** When a job escalates, store the cloud result beside
   the local attempt, both keyed to the same brief. That pair is the raw
   material for everything else, and is useful on its own as an
   art-direction target.

2. **Prompt distillation.** Send the brief, the local attempt and the cloud
   result to Claude and ask what the local prompt should have said. This is the
   loop with the best return for the money: it is cheap, it runs on text, and
   prompt quality is responsible for a large share of the visible gap.
   `prompt_assist.py` already has the shape — it currently runs on local
   Ollama, and would take a cloud provider as a second backend.

3. **Recipe search.** Hold the prompt fixed and vary what the workflow JSON
   controls: steps, CFG, sampler, resolution, refiner, upscaler. Score each
   against the stored reference. Keep the winning combination as a named
   preset. This is where real, retained local improvement comes from, and it
   costs nothing beyond local GPU time once the reference exists.

The honest framing: the system learns **recipes**, not **weights**. Over a few
dozen escalations that is a visible quality gain on the local path, and the
escalation rate should fall as a result — which is the actual goal.

## 5. Build order

Each step is useful alone and testable before the next.

1. `escalation.py` with `decide()` and the guards. Pure logic, no network. Full
   unit coverage including every refuse-to-escalate case.
2. The spend ledger entry type and the ceilings.
3. Wire `on_failure` into the image path only — `generators/__init__.py`, the
   seam that already exists — with policy defaulting to `off`.
4. Reference capture on every escalation.
5. Prompt distillation via Claude.
6. Recipe search and preset promotion.
7. Extend to video and avatar once the image path has run for a while.

## 6. Decisions still David's to make

- Switch `on_failure` on, or keep every escalation at `ask`?
- The daily ceiling, in each provider's units.
- Does a family user get to spend cloud credits, or is escalation
  owner-only? The current router is admin-only; the escalation path would be
  the first thing to widen that, and probably should not.

## 7. Why none of this is implemented in this branch

Every file it touches — `integrations.py`, `cloud_media.py`, `config.py`,
`generators/__init__.py` — is a file `amd-sync` also edits. That branch differs
from `master` across 1,054 files. Writing the feature here would guarantee a
painful conflict and would duplicate work already done.

The sequence that avoids that: land `amd-sync`, land the 29 R9700 commits, then
build section 3 on top of the merged result. Until then this document is the
specification, and it is deliberately written against interfaces that already
exist so it can be implemented directly rather than redesigned.
