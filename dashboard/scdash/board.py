"""Stage 3's one entry point for the service: everything the page needs beyond today's state.

    payload = board.build(reader.state, plans, user_block, now, game_running)

- `state`: the LogReader's State.
- `plan`: a plan.PlanStore (its `.plan` and `.notice` are used), a plan dict as
  plan.normalize() returns it, or None.
- `user`: the `user` block of data/state.json (quick timers, a view picked by hand); read with
  plan.clean_user(), so anything malformed in it is ignored.
- `now`: seconds since the epoch, from the service's clock (the replay clock in a replay).
- `game_running`: whether the game process is running (the service knows; the log alone does
  not, since a crash leaves no line).

A pure function of those: the same inputs give the same payload. It reads no clock and no
file except the reference tables (loaded once, PLAN §9). The payload changes with `now` only at
the moments `next_change_ms` names (an alert expiring, a timer coming due), so the service
rebuilds it when the state changed or when that moment has passed, and not every second.

Its keys are described in dashboard/STATE.md. Every text in it has gone through the state's
scrubber: other players' names read "another player", the user's handle "you", and no control
or bidi character survives (PLAN §8).
"""
from . import alerts as alertlib
from . import rules
from . import views
import math

from .plan import PlanStore, clean_user, current_run, quick_timer
from .words import iso, next_midnight

SCHEMA = 1


MAX_TEXT = 300            # every text in the payload, whatever the log or the plan said


MIN_NOW, MAX_NOW = 31536000.0, 4102444800.0      # 1971 to 2099: a time every date function can word


def build(state, plan=None, user=None, now=None, game_running=True, tz=None):
    if now is None:
        raise ValueError("build() needs `now`: the state never reads the clock (PLAN §7)")
    if isinstance(plan, PlanStore):
        plan_obj, notice = plan.plan, plan.notice
    else:
        plan_obj, notice = plan, None
    problems = []
    if not (isinstance(now, (int, float)) and math.isfinite(now) and MIN_NOW <= now <= MAX_NOW):
        # A clock no date can show (not finite, before 1971, past 2099): the last event's time
        # stands in, so the page still gets a payload, and the service logs the problem.
        problems.append("now: not a usable time")
        now = state.session["last_t"] or MIN_NOW
    try:
        payload = _build(state, plan_obj, notice, user, now, game_running, tz, problems)
    except Exception as e:                         # noqa: BLE001 - the page gets something, always
        payload = {"schema": SCHEMA,
                   "view": {"name": "now", "rule": "error", "why": "The payload could not be built",
                            "context": "error", "auto": "now", "mode": "flight", "picked": False,
                            "pick_dropped": False},
                   "model": {"view": "now", "unavailable": True}, "strip": None, "alerts": [], "timers": [],
                   "plan": {"loaded": plan_obj is not None, "notice": notice, "updated": None,
                            "updated_text": None, "run": None, "run_kind": None},
                   "unmapped_contracts": [], "next_change_ms": None,
                   "problems": problems + ["build: %s" % e.__class__.__name__]}
    return _clip(state.scrub(payload))


def _clip(x):
    if isinstance(x, str):
        return x if len(x) <= MAX_TEXT else x[:MAX_TEXT - 1] + "…"
    if isinstance(x, dict):
        return {k: _clip(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_clip(v) for v in x]
    return x


def _build(state, plan_obj, notice, user, now, game_running, tz, problems):
    u = clean_user(user)
    view, facts = rules.choose(state, plan_obj, u["view"], game_running)
    # One part that fails must not blank the page: it is left empty and named in `problems`
    # (the service logs them). The view rules above have no such guard: they are the page.
    timers, t_next = _guarded(problems, "timers", lambda: alertlib.build_timers(state, plan_obj, u, now, tz), ([], None))
    alerts, a_next = _guarded(problems, "alerts", lambda: alertlib.build_alerts(state, now, game_running, tz), ([], None))
    ctx = views.Ctx(state, plan_obj, facts, now, tz, timers)
    model = _guarded(problems, "model", lambda: views.model(ctx, view["name"], view),
                     {"view": view["name"], "unavailable": True})
    strip = _guarded(problems, "strip", lambda: views.strip(ctx, view["name"]), None)
    run = current_run(plan_obj)
    # Every worded time switches from "10:24 PM" to "Nov 26, 10:24 PM" at local midnight, so the
    # payload changes then too (stage 3 review).
    nxt = [t for t in (t_next, a_next, next_midnight(now, tz)) if t is not None]
    updated = (plan_obj or {}).get("updated_t")
    payload = {
        "schema": SCHEMA,
        "view": view,
        "model": model,
        "strip": strip,
        "alerts": alerts,
        "timers": timers,
        "plan": {"loaded": plan_obj is not None, "notice": notice,
                 "updated": iso(updated), "updated_text": ctx.when(updated) if updated else None,
                 "run": run["name"] if run else None, "run_kind": run["kind"] if run else None},
        "unmapped_contracts": state.unmapped_contracts(),
        "next_change_ms": int(round(min(nxt) * 1000)) if nxt else None,
        "problems": problems,
    }
    return payload


def _guarded(problems, what, make, fallback):
    try:
        return make()
    except Exception as e:                         # noqa: BLE001 - a bug in one part, not the page
        problems.append("%s: %s" % (what, e.__class__.__name__))
        return fallback


def pick(state, plan, view, game_running=True, now=None):
    """What to save in the user block as `view` when the user picks a view by hand. It stays
    picked until the context changes (rules.choose); "reference" stays until "live" is picked.
    None for "live" (save None: the rules choose again) and for a name that is not a view."""
    plan_obj = plan.plan if isinstance(plan, PlanStore) else plan
    return rules.pick(state, plan_obj, view, game_running, at=iso(now) if now is not None else None)


def add_quick_timer(user, label, minutes, now):
    """The user block with one more quick timer (the oldest dropped past the cap), or None when
    the label or the length is not acceptable. The service saves the result."""
    from .plan import MAX_QUICK
    out = dict(user) if isinstance(user, dict) else {}
    timers = [x for x in (out.get("timers") or []) if isinstance(x, dict)] if isinstance(out.get("timers"), list) else []
    t = quick_timer(label, minutes, now, taken={x.get("id") for x in timers if isinstance(x.get("id"), str)})
    if t is None:
        return None
    timers.append(t)
    out["timers"] = timers[-MAX_QUICK:]
    return out


def remove_quick_timer(user, timer_id):
    """The user block without the quick timer of that id ('quick:<id>' or '<id>')."""
    out = dict(user) if isinstance(user, dict) else {}
    tid = timer_id[6:] if isinstance(timer_id, str) and timer_id.startswith("quick:") else timer_id
    out["timers"] = [x for x in (out.get("timers") or []) if isinstance(x, dict) and x.get("id") != tid] \
        if isinstance(out.get("timers"), list) else []
    return out
