"""Offline tests for ticket_roles. Run: python3 test_ticket_roles_offline.py"""

import sys
import ticket_roles as R

ALICE, BOB, CAROL = "alice", "bob", "carol"


def tk(**kw):
    t = {"id": "T1", "created_by": ALICE, "claimed_by": None, "assigned_to": None}
    t.update(kw)
    return t


def denied(current, target, **kw):
    ok, basis = R.can_transition(current, target, **kw)
    assert not ok, f"expected denial for {current}->{target}, got basis={basis!r}"
    return basis


def allowed(current, target, **kw):
    ok, basis = R.can_transition(current, target, **kw)
    assert ok, f"expected {current}->{target} allowed, got {basis!r}"
    return basis


# --- shape of the machine ------------------------------------------------

def test_illegal_shape_is_rejected():
    denied("open", "closed", agent_name=ALICE, ticket=tk())
    denied("open", "submitted", agent_name=ALICE, ticket=tk())


def test_terminal_states_are_terminal():
    for state in ("closed", "canceled", "terminated"):
        msg = denied(state, "in_progress", agent_name=ALICE,
                     ticket=tk(), is_coordinator=True)
        assert "terminal" in msg


def test_unknown_target_rejected():
    assert "unknown target" in denied("open", "banana", agent_name=ALICE, ticket=tk())


# --- THE property: completed != success ----------------------------------

def test_executor_cannot_close_its_own_work():
    t = tk(created_by=ALICE, claimed_by=BOB)
    msg = denied("submitted", "closed", agent_name=BOB, ticket=t)
    assert "completed != success" in msg
    assert "alice" in msg          # tells bob who to ask


def test_executor_cannot_review_or_reject_its_own_work():
    t = tk(created_by=ALICE, claimed_by=BOB)
    for target in ("reviewing", "rejected"):
        denied("submitted", target, agent_name=BOB, ticket=t)


def test_owner_reviews_and_closes():
    t = tk(created_by=ALICE, claimed_by=BOB)
    assert allowed("submitted", "reviewing", agent_name=ALICE, ticket=t) == "owner"
    assert allowed("submitted", "closed", agent_name=ALICE, ticket=t) == "owner"


def test_coordinator_may_adjudicate_a_ticket_it_never_touched():
    t = tk(created_by=ALICE, claimed_by=BOB)
    assert allowed("submitted", "closed", agent_name=CAROL, ticket=t,
                   is_coordinator=True) == "coordinator"
    denied("submitted", "closed", agent_name=CAROL, ticket=t)   # plain agent


# --- stacked hats cannot launder the conflict ----------------------------

def test_owner_who_also_executed_still_blocked_by_default():
    """The case the bridge never had to handle: owner == executor."""
    t = tk(created_by=ALICE, claimed_by=ALICE)
    msg = denied("submitted", "closed", agent_name=ALICE, ticket=t)
    assert "allow_self_review" in msg      # the escape hatch is discoverable


def test_denial_does_not_tell_the_owner_to_ask_itself():
    """When owner == executor, naming them reads as a broken message.

    The lookup was always correct — it reports created_by — but on a solo
    create -> claim -> do cycle that is the same agent being told to go ask
    itself. Solo users hit this string on every ticket, so it is the most-read
    denial in the system.
    """
    t = tk(created_by=ALICE, claimed_by=ALICE)
    msg = denied("submitted", "closed", agent_name=ALICE, ticket=t)
    assert f"Ask `{ALICE}`" not in msg
    assert "another main/lead/reviewer agent" in msg


def test_denial_still_names_a_different_owner():
    """The narrow fix must not cost the useful case: a real person to ask."""
    t = tk(created_by=ALICE, claimed_by=BOB)
    msg = denied("submitted", "closed", agent_name=BOB, ticket=t)
    assert f"`{ALICE}`" in msg


def test_self_review_is_possible_but_marked():
    t = tk(created_by=ALICE, claimed_by=ALICE)
    basis = allowed("submitted", "closed", agent_name=ALICE, ticket=t,
                    allow_self_review=True)
    assert "SELF-REVIEWED" in basis        # the audit records that nobody checked


def test_self_review_does_not_help_a_bare_executor():
    """bob executed but neither owns nor coordinates — the flag must not apply."""
    t = tk(created_by=ALICE, claimed_by=BOB)
    msg = denied("submitted", "closed", agent_name=BOB, ticket=t,
                 allow_self_review=True)
    assert "does not apply" in msg


# --- execution side ------------------------------------------------------

def test_executor_drives_work_forward():
    t = tk(created_by=ALICE, claimed_by=BOB)
    assert allowed("claimed", "in_progress", agent_name=BOB, ticket=t) == "executor"
    assert allowed("in_progress", "submitted", agent_name=BOB, ticket=t) == "executor"


def test_bystander_cannot_submit_work_it_did_not_do():
    t = tk(created_by=ALICE, claimed_by=BOB)
    denied("in_progress", "submitted", agent_name=CAROL, ticket=t)


def test_owner_cannot_submit_on_the_executors_behalf():
    t = tk(created_by=ALICE, claimed_by=BOB)
    denied("in_progress", "submitted", agent_name=ALICE, ticket=t)


# --- assignment gate -----------------------------------------------------

def test_anyone_claims_from_the_open_queue():
    assert allowed("open", "claimed", agent_name=CAROL, ticket=tk()) == "queue"


def test_assigned_ticket_is_not_up_for_grabs():
    t = tk(assigned_to=BOB)
    assert "assigned to" in denied("open", "claimed", agent_name=CAROL, ticket=t)
    allowed("open", "claimed", agent_name=BOB, ticket=t)
    allowed("open", "claimed", agent_name=CAROL, ticket=t, is_coordinator=True)


# --- reopen / retry ------------------------------------------------------

def test_owner_reopens_a_rejected_ticket_and_executor_retries():
    t = tk(created_by=ALICE, claimed_by=BOB)
    allowed("reviewing", "rejected", agent_name=ALICE, ticket=t)
    assert allowed("rejected", "in_progress", agent_name=BOB, ticket=t) == "executor"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  ok    {name}")
        except Exception as exc:
            failed.append(name)
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
