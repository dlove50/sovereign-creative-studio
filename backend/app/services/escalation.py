"""Decide whether a failed local job should be retried on a paid cloud provider.

David's ask: keep the work local on the R9700, but use the Claude / OpenAI /
HeyGen / ElevenLabs accounts when the hardware genuinely cannot produce what is
needed. See docs/CLOUD_ESCALATION_DESIGN.md for the whole design; this is §3,
the part that decides.

`cloud_media.py` opens with "no model extraction, automatic retries or paid
fallbacks". That was a deliberate decision and a good one -- a crash loop that
escalates on every retry is how a credit balance disappears overnight. This
module reverses it only where David asked, and keeps the intent via the guards
below rather than by deleting the line.

This module decides and nothing else. It calls no provider, spends nothing,
writes nothing, and never raises. That matters for two reasons: the decision is
the part with the money attached, so it should be testable without a network;
and an exception escaping a failure handler would turn a recoverable local
failure into a lost job.

The guards, in the order they are applied -- each can only ever say no:

  1. KILL SWITCH   one setting stops all escalation, for a runaway.
  2. POLICY        off / ask / on_failure / auto. Defaults to off.
  3. CLASSIFY      only capability and capacity failures escalate. A bad
                   prompt fails identically on a cloud GPU, so paying for it
                   buys nothing. This is the guard that stops a retry loop
                   costing money.
  4. ONCE PER JOB  a job that has already escalated never escalates again,
                   whatever happens next. The single most important guard.
  5. CEILINGS      per-job and per-day spend limits, refused at the limit
                   rather than queued.
  6. ROUTE         a provider that can actually do this kind of work, is
                   configured, and is enabled.

Nothing here is time-based or stateful: the caller supplies what it knows via
SpendState, so the same inputs always produce the same decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --- policies ---------------------------------------------------------------
POLICY_OFF = "off"            # never escalate. The default.
POLICY_ASK = "ask"            # offer on any escalatable failure; spend nothing
POLICY_ON_FAILURE = "on_failure"  # escalate automatically on hardware failure
POLICY_AUTO = "auto"          # also escalate on a quality verdict
POLICIES = (POLICY_OFF, POLICY_ASK, POLICY_ON_FAILURE, POLICY_AUTO)

# --- failure classification -------------------------------------------------
# The reference: a failure escalates only if a different, larger machine would
# plausibly succeed where this one did not.
#
# Capacity and capability failures -- the hardware could not do it.
ESCALATABLE_FAILURES = frozenset({
    "oom",                # the host or cgroup killed it
    "vram_exhausted",     # the card ran out
    "svm_wedge",          # the KFD restore livelock on this box
    "timeout",            # exceeded the poll budget
    "gpu_unavailable",    # /dev/kfd unreachable, driver wedged
    "quality_rejected",   # a human or scorer judged the local result unusable
})

# Input and configuration failures -- a cloud GPU fails these the same way, so
# escalating only converts a free failure into a paid one. Kept explicit rather
# than inferred, so adding a failure kind is a deliberate decision.
NEVER_ESCALATE_FAILURES = frozenset({
    "bad_prompt",         # rejected by a safety filter or empty
    "invalid_input",      # malformed request, bad dimensions
    "missing_model",      # a weights file is not installed
    "malformed_workflow", # the graph JSON is wrong
    "auth_error",         # our own credentials are broken
    "cancelled",          # somebody stopped it on purpose
    "insufficient_credits",
})

# `quality_rejected` is the one failure that is about the result rather than the
# machine, so it needs the strongest policy. Spending money because a render
# came out ugly should be a deliberate setting, not a side effect of enabling
# crash recovery.
REQUIRES_AUTO_POLICY = frozenset({"quality_rejected"})

# --- routing ----------------------------------------------------------------
# Which provider can actually do each kind of work. Claude Code and Codex are
# deliberately absent: they are coding agents and cannot render anything.
PROVIDER_FOR_JOB = {
    "image": "openai",
    "product_scene": "openai",
    "avatar_video": "heygen",
    "voice": "elevenlabs",
    "tts": "elevenlabs",
    "dubbing": "elevenlabs",
    "copy": "anthropic",
}


@dataclass(frozen=True)
class SpendState:
    """What the caller knows about money and history. All of it is required.

    `already_escalated_job_ids` is the persisted set behind guard 4. Passing an
    empty set means "this job has never escalated", so a caller that forgets to
    load it would silently disable the most important guard -- hence no default.
    """

    spent_today: float
    daily_ceiling: float
    per_job_ceiling: float
    estimated_cost: float
    already_escalated_job_ids: frozenset[str]
    configured_providers: frozenset[str]   # has an API key
    enabled_providers: frozenset[str]      # admin switched it on


@dataclass(frozen=True)
class Decision:
    """Why escalation was or was not chosen. The reason is user-facing."""

    escalate: bool
    reason: str
    provider: str | None = None
    needs_consent: bool = False
    estimated_cost: float | None = None
    guard: str | None = None   # which guard refused, for logs and tests

    @property
    def spends_money_now(self) -> bool:
        """True only when the caller may bill without asking first."""
        return self.escalate and not self.needs_consent


def _refuse(reason: str, guard: str) -> Decision:
    return Decision(escalate=False, reason=reason, guard=guard)


def decide(
    *,
    job_kind: str,
    failure: str | None,
    policy: str,
    spend: SpendState,
    job_id: str,
    kill_switch: bool = False,
) -> Decision:
    """Whether to retry `job_id` on a cloud provider. Pure; never raises."""

    # Guard 1 -- the kill switch, first so it cannot be reasoned around.
    if kill_switch:
        return _refuse("Cloud escalation is switched off.", "kill_switch")

    # Guard 2 -- policy. An unknown policy string is treated as off rather
    # than as permission, so a typo in config cannot start spending.
    if policy not in POLICIES:
        return _refuse(
            f"Unknown escalation policy {policy!r}; treating as off.", "policy"
        )
    if policy == POLICY_OFF:
        return _refuse("Escalation policy is off.", "policy")

    # Guard 3 -- classify. Nothing escalates without a failure to escalate.
    if failure is None:
        return _refuse("Nothing failed, so there is nothing to escalate.",
                       "classify")
    if failure in NEVER_ESCALATE_FAILURES:
        return _refuse(
            f"A {failure.replace('_', ' ')} fails the same way on a cloud "
            "provider, so escalating would only cost money.",
            "classify",
        )
    if failure not in ESCALATABLE_FAILURES:
        # Unrecognised failures do not escalate. New failure kinds should be
        # classified deliberately, not default into spending.
        return _refuse(
            f"Failure {failure!r} is not classified as escalatable.", "classify"
        )
    if failure in REQUIRES_AUTO_POLICY and policy != POLICY_AUTO:
        return _refuse(
            "Escalating on result quality needs the 'auto' policy; this is a "
            "judgement about the output, not a hardware failure.",
            "policy",
        )

    # Guard 4 -- once per job, ever. Placed before the ceilings so a retry
    # loop is refused even while budget remains.
    if job_id in spend.already_escalated_job_ids:
        return _refuse(
            "This job has already been escalated once; it will not be sent "
            "again.",
            "once_per_job",
        )

    # Guard 5 -- ceilings.
    if spend.estimated_cost > spend.per_job_ceiling:
        return _refuse(
            f"Estimated {spend.estimated_cost:.2f} exceeds the per-job limit "
            f"of {spend.per_job_ceiling:.2f}.",
            "per_job_ceiling",
        )
    if spend.spent_today + spend.estimated_cost > spend.daily_ceiling:
        return _refuse(
            f"Today's spend of {spend.spent_today:.2f} plus "
            f"{spend.estimated_cost:.2f} would pass the daily limit of "
            f"{spend.daily_ceiling:.2f}.",
            "daily_ceiling",
        )

    # Guard 6 -- route to a provider that can do this work and is ready.
    provider = PROVIDER_FOR_JOB.get(job_kind)
    if provider is None:
        return _refuse(
            f"No cloud provider handles {job_kind!r} work.", "route"
        )
    if provider not in spend.configured_providers:
        return _refuse(
            f"{provider} has no API key configured.", "route"
        )
    if provider not in spend.enabled_providers:
        return _refuse(
            f"{provider} is configured but not enabled.", "route"
        )

    # Every guard passed. Under 'ask' the answer is still yes -- but the
    # caller must obtain consent before spending.
    needs_consent = policy == POLICY_ASK
    verb = "Can retry" if needs_consent else "Retrying"
    return Decision(
        escalate=True,
        reason=(
            f"{verb} on {provider} after a local {failure.replace('_', ' ')}. "
            f"Estimated {spend.estimated_cost:.2f}."
        ),
        provider=provider,
        needs_consent=needs_consent,
        estimated_cost=spend.estimated_cost,
    )
