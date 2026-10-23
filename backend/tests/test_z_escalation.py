"""Escalation guards. Every assertion here is about money.

The failure mode this protects against is a local crash loop quietly becoming a
bill: ComfyUI OOMs, the job retries, each retry escalates, and the credit
balance is gone by morning. So the tests care most about the refusals, and
specifically about the order they are applied in -- a ceiling check that runs
before the once-per-job check would let a retry loop spend right up to the
limit every day.

Default posture is also pinned: an unset policy, an unknown policy string and
an unrecognised failure kind must all refuse. Permission has to be granted
explicitly, never fallen into.
"""
from __future__ import annotations

import os
import sys
import tempfile

if "app.config" not in sys.modules:
    _TMP = tempfile.mkdtemp()
    os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
    os.environ["STORAGE_DIR"] = os.path.join(_TMP, "storage")

import pytest  # noqa: E402

from app.services import escalation as esc  # noqa: E402


def _spend(**overrides) -> esc.SpendState:
    """A state where everything is permitted, so each test breaks one thing."""
    base = dict(
        spent_today=0.0,
        daily_ceiling=100.0,
        per_job_ceiling=10.0,
        estimated_cost=1.0,
        already_escalated_job_ids=frozenset(),
        configured_providers=frozenset({"openai", "heygen", "elevenlabs", "anthropic"}),
        enabled_providers=frozenset({"openai", "heygen", "elevenlabs", "anthropic"}),
    )
    base.update(overrides)
    return esc.SpendState(**base)


def _decide(**overrides):
    base = dict(
        job_kind="image",
        failure="oom",
        policy=esc.POLICY_ON_FAILURE,
        spend=_spend(),
        job_id="job-1",
    )
    base.update(overrides)
    return esc.decide(**base)


# --------------------------------------------------------------------------
# The happy path, so the refusal tests mean something
# --------------------------------------------------------------------------

def test_a_hardware_failure_escalates_under_on_failure():
    d = _decide()
    assert d.escalate
    assert d.provider == "openai"
    assert d.needs_consent is False
    assert d.spends_money_now is True
    assert d.guard is None


def test_ask_policy_escalates_but_withholds_the_spend():
    """The distinction that keeps unattended money safe."""
    d = _decide(policy=esc.POLICY_ASK)
    assert d.escalate is True
    assert d.needs_consent is True
    assert d.spends_money_now is False, "ask must never bill without consent"
    assert "Can retry" in d.reason


# --------------------------------------------------------------------------
# Guard 1 and 2: the switches
# --------------------------------------------------------------------------

def test_the_kill_switch_beats_every_policy():
    for policy in esc.POLICIES:
        d = _decide(policy=policy, kill_switch=True)
        assert not d.escalate
        assert d.guard == "kill_switch"


def test_off_is_the_default_posture():
    d = _decide(policy=esc.POLICY_OFF)
    assert not d.escalate and d.guard == "policy"


@pytest.mark.parametrize("typo", ["", "ON_FAILURE", "on-failure", "yes", "true", None])
def test_an_unknown_policy_refuses_rather_than_permits(typo):
    """A config typo must not be read as permission to spend."""
    d = _decide(policy=typo)
    assert not d.escalate, f"{typo!r} was treated as permission"
    assert d.guard == "policy"


# --------------------------------------------------------------------------
# Guard 3: classification -- the guard that stops a retry loop costing money
# --------------------------------------------------------------------------

@pytest.mark.parametrize("failure", sorted(esc.ESCALATABLE_FAILURES - esc.REQUIRES_AUTO_POLICY))
def test_capacity_and_capability_failures_escalate(failure):
    assert _decide(failure=failure).escalate, f"{failure} should escalate"


@pytest.mark.parametrize("failure", sorted(esc.NEVER_ESCALATE_FAILURES))
def test_input_failures_never_escalate(failure):
    """These fail identically on a cloud GPU, so paying converts free to paid."""
    d = _decide(failure=failure, policy=esc.POLICY_AUTO)
    assert not d.escalate, f"{failure} would have been paid for"
    assert d.guard == "classify"


def test_no_failure_means_nothing_to_escalate():
    d = _decide(failure=None)
    assert not d.escalate and d.guard == "classify"


def test_an_unrecognised_failure_refuses():
    """New failure kinds must be classified deliberately, not default to spend."""
    d = _decide(failure="something_nobody_has_seen_before", policy=esc.POLICY_AUTO)
    assert not d.escalate and d.guard == "classify"


def test_the_two_classifications_cannot_overlap():
    """A failure in both sets would make behaviour depend on check order."""
    assert not (esc.ESCALATABLE_FAILURES & esc.NEVER_ESCALATE_FAILURES)


def test_quality_rejection_needs_the_auto_policy():
    """Spending because a render came out ugly is a separate decision from
    spending because the GPU died."""
    assert not _decide(failure="quality_rejected", policy=esc.POLICY_ON_FAILURE).escalate
    assert _decide(failure="quality_rejected", policy=esc.POLICY_AUTO).escalate


# --------------------------------------------------------------------------
# Guard 4: once per job, ever
# --------------------------------------------------------------------------

def test_a_job_escalates_at_most_once():
    d = _decide(spend=_spend(already_escalated_job_ids=frozenset({"job-1"})))
    assert not d.escalate
    assert d.guard == "once_per_job"


def test_the_once_guard_applies_under_every_policy_and_failure():
    """A retry loop must not find a combination that gets through."""
    spent = _spend(already_escalated_job_ids=frozenset({"job-1"}))
    for policy in (esc.POLICY_ASK, esc.POLICY_ON_FAILURE, esc.POLICY_AUTO):
        for failure in sorted(esc.ESCALATABLE_FAILURES):
            d = _decide(policy=policy, failure=failure, spend=spent)
            assert not d.escalate, f"{policy}/{failure} escaped the once guard"


def test_the_once_guard_is_checked_before_the_ceilings():
    """Order matters: a loop with budget left must still be refused for being
    a repeat, not pass the repeat check and get stopped by cost."""
    d = _decide(spend=_spend(
        already_escalated_job_ids=frozenset({"job-1"}),
        estimated_cost=999.0,       # would also trip the per-job ceiling
    ))
    assert d.guard == "once_per_job", (
        "the repeat was refused on cost; a cheaper repeat would have gone through")


def test_other_jobs_are_unaffected_by_a_sibling_escalation():
    d = _decide(job_id="job-2",
                spend=_spend(already_escalated_job_ids=frozenset({"job-1"})))
    assert d.escalate


# --------------------------------------------------------------------------
# Guard 5: ceilings
# --------------------------------------------------------------------------

def test_a_job_over_the_per_job_ceiling_is_refused():
    d = _decide(spend=_spend(estimated_cost=11.0, per_job_ceiling=10.0))
    assert not d.escalate and d.guard == "per_job_ceiling"


def test_the_daily_ceiling_counts_what_this_job_would_add():
    """Checking spent_today alone would let one job blow straight past it."""
    d = _decide(spend=_spend(spent_today=99.5, estimated_cost=1.0,
                             daily_ceiling=100.0))
    assert not d.escalate and d.guard == "daily_ceiling"


def test_spending_exactly_to_the_ceiling_is_allowed():
    """A limit is a limit, not a limit minus one."""
    assert _decide(spend=_spend(spent_today=99.0, estimated_cost=1.0,
                                daily_ceiling=100.0)).escalate
    assert _decide(spend=_spend(estimated_cost=10.0,
                                per_job_ceiling=10.0)).escalate


def test_a_zero_ceiling_refuses_everything_with_a_cost():
    d = _decide(spend=_spend(daily_ceiling=0.0, estimated_cost=0.01))
    assert not d.escalate


# --------------------------------------------------------------------------
# Guard 6: routing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("job_kind,provider", sorted(esc.PROVIDER_FOR_JOB.items()))
def test_each_job_kind_routes_to_its_provider(job_kind, provider):
    assert _decide(job_kind=job_kind).provider == provider


def test_an_unroutable_job_kind_is_refused():
    d = _decide(job_kind="music")
    assert not d.escalate and d.guard == "route"


def test_an_unconfigured_provider_is_refused():
    d = _decide(spend=_spend(configured_providers=frozenset()))
    assert not d.escalate and d.guard == "route"
    assert "no API key" in d.reason


def test_a_configured_but_disabled_provider_is_refused():
    d = _decide(spend=_spend(enabled_providers=frozenset()))
    assert not d.escalate and d.guard == "route"
    assert "not enabled" in d.reason


def test_coding_agents_are_not_render_providers():
    """Claude Code and Codex cannot produce a frame; they must never be routed."""
    routed = set(esc.PROVIDER_FOR_JOB.values())
    assert not routed & {"claude_code", "codex", "claude-code"}


# --------------------------------------------------------------------------
# Properties that hold across the whole input space
# --------------------------------------------------------------------------

def test_a_refusal_always_explains_itself():
    """A silent refusal is unactionable; a named guard is debuggable."""
    for failure in [None, "weird", *sorted(esc.NEVER_ESCALATE_FAILURES)]:
        d = _decide(failure=failure)
        assert not d.escalate
        assert d.reason.strip(), "refused with an empty reason"
        assert d.guard, "refused without naming the guard"


def test_a_refusal_never_names_a_provider_or_a_cost():
    """So a caller cannot read a refusal and bill against it anyway."""
    d = _decide(policy=esc.POLICY_OFF)
    assert d.provider is None
    assert d.estimated_cost is None
    assert d.spends_money_now is False


def test_decide_never_raises_on_hostile_input():
    """It runs inside a failure handler; an exception here loses the job."""
    for kwargs in (
        dict(job_kind="", failure="", policy=""),
        dict(job_kind=None, failure=None, policy=None),
        dict(job_id=""),
        dict(spend=_spend(estimated_cost=-5.0)),
        dict(spend=_spend(daily_ceiling=-1.0, per_job_ceiling=-1.0)),
        dict(job_kind="image", failure="oom", policy=esc.POLICY_AUTO, job_id="x" * 500),
    ):
        d = _decide(**kwargs)
        assert isinstance(d, esc.Decision)
