"""Governed settings: the values a risk committee owns, changed by maker and checker (TODO C3).

Two kinds of value are editable from the Settings screen, each on its own route:

  * risk appetite    the bad-rate ceiling and the multiples under it. One person proposes a new
                     value with a reason; a second person approves or rejects it. The person who
                     proposed a change can withdraw it but never approve it.
  * replay assumptions  what the engine does where the rule files are silent. Only the risk
                     approver changes these, directly, and every change is recorded.

An approved value does not move any figure by itself. It takes effect on the next recompute,
when the engine rebuilds on `effective(config)`: the config file with every approved value laid
over it. Until then the screen says the value is approved and waiting, so nobody reads a figure
as if it already used it.

Every proposal, decision and direct change is kept, with who and when, in one JSON file (config
`policy.path`). Nothing is ever removed from it: the history of a value is the audit of it.
Until the server authenticates people, `who` is the name the page sends; separation of duties
is enforced on it here, and the field is where the ABAC identity goes.
"""
from __future__ import annotations

import copy
import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

MAX_REASON = 280
HISTORY = 50                   # how many records the screen is sent, newest first


class PolicyError(ValueError):
    """A proposal, decision or change the store refuses. The message says why, in words."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Setting:
    key: str
    path: tuple[str, str]      # where the value sits in the client config
    group: str                 # appetite · advanced · assumption
    label: str
    unit: str                  # rate · multiple · bool
    help: str
    lo: float | None = None
    hi: float | None = None

    @property
    def route(self) -> str:
        return "direct" if self.group == "assumption" else "maker-checker"

    def read(self, cfg: dict):
        return cfg[self.path[0]][self.path[1]]

    def clean(self, value):
        """A proposed value in the setting's own type, or a refusal that says what is allowed."""
        if self.unit == "bool":
            if not isinstance(value, bool):
                raise PolicyError(f"{self.label} is yes or no")
            return value
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise PolicyError(f"{self.label} must be a number") from None
        if not np.isfinite(v) or not (self.lo <= v <= self.hi):
            show = (lambda x: f"{x:.0%}") if self.unit == "rate" else (lambda x: f"{x:.2f}×")
            raise PolicyError(f"{self.label} must be between {show(self.lo)} and {show(self.hi)}")
        return round(v, 4 if self.unit == "rate" else 2)


SETTINGS: dict[str, Setting] = {s.key: s for s in (
    Setting("bad_rate_ceiling", ("optimise", "max_bad_rate"), "appetite", "Bad-rate ceiling", "rate",
            "No recommended strategy may exceed this expected bad rate.", 0.01, 0.40),
    Setting("earns_place_multiple", ("drivers", "earns_place_multiple"), "advanced",
            "A rule earns its place above", "multiple",
            "A rule keeps its place if the applicants it alone declines are at least this many "
            "times riskier than the booked book.", 1.0, 5.0),
    Setting("riskier_multiple", ("simulate", "riskier_multiple"), "advanced", "Riskier swap-ins above",
            "multiple", "Newly approved applicants above this multiple of the booked bad rate are "
            "called riskier.", 1.0, 5.0),
    Setting("safer_multiple", ("simulate", "safer_multiple"), "advanced", "Safer swap-ins below",
            "multiple", "Newly approved applicants below this multiple are called safer.", 0.1, 1.0),
    Setting("missing_value_matches", ("replay", "condition_on_missing_value_matches"), "assumption",
            "When a rule tests a value the applicant does not have, the rule applies", "bool",
            "Yes: an applicant with no bureau score is caught by every rule on the score. "
            "No: they pass those rules."),
    Setting("include_inactive_rules", ("replay", "include_inactive_rules"), "assumption",
            "Replay the rules marked inactive in the rule files", "bool",
            "No keeps them off, as in production."),
)}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def setting(key) -> Setting:
    if key not in SETTINGS:
        raise PolicyError(f"{key!r} is not a setting that can be changed here", 404)
    return SETTINGS[key]


def apply(cfg: dict, records: list[dict]) -> dict:
    """The config with every approved value laid over it, in the order they were approved."""
    out = copy.deepcopy(cfg)
    for r in records:
        if r["status"] == "approved" and r["setting"] in SETTINGS:
            a, b = SETTINGS[r["setting"]].path
            out[a][b] = r["to"]
    return out


class PolicyStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ file
    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise PolicyError(f"the settings history {self.path.name} is damaged: {e}", 500) from None
        return data.get("changes", []) if isinstance(data, dict) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"changes": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def records(self) -> list[dict]:
        with self._lock:
            return self._read()

    def effective(self, cfg: dict) -> dict:
        return apply(cfg, self.records())

    # ------------------------------------------------------------------ changes
    def propose(self, key, to, reason, who, cfg: dict) -> dict:
        s = setting(key)
        if s.route != "maker-checker":
            raise PolicyError(f"{s.label} is changed by the risk approver directly, not proposed")
        if not who:
            raise PolicyError("say who is proposing the change")
        reason = str(reason or "").strip()
        if not reason:
            raise PolicyError("give a reason: the approver reads it")
        if len(reason) > MAX_REASON:
            raise PolicyError(f"a reason is at most {MAX_REASON} characters")
        value = s.clean(to)
        with self._lock:
            rows = self._read()
            now = s.read(apply(cfg, rows))
            if value == now:
                raise PolicyError(f"{s.label} is already {fmt(s, now)}")
            if any(r["setting"] == key and r["status"] == "pending" for r in rows):
                raise PolicyError(f"a change to {s.label} is already waiting for approval", 409)
            row = {"id": uuid.uuid4().hex[:12], "setting": key, "route": s.route, "from": now, "to": value,
                   "reason": reason, "status": "pending", "proposed_by": who, "proposed_at": _now(),
                   "decided_by": None, "decided_at": None, "note": None}
            rows.append(row)
            self._write(rows)
        return row

    def decide(self, cid, approve, who, note=None, cfg: dict | None = None) -> dict:
        """Approve or reject a pending proposal. Its proposer may only withdraw it."""
        if not who:
            raise PolicyError("say who is deciding")
        with self._lock:
            rows = self._read()
            row = next((r for r in rows if r["id"] == cid), None)
            if row is None:
                raise PolicyError(f"no proposed change {cid!r}", 404)
            if row["status"] != "pending":
                raise PolicyError(f"that change was already {row['status']}", 409)
            own = who == row["proposed_by"]
            if own and approve:
                raise PolicyError("a change needs a second person: whoever proposed it cannot approve it", 403)
            # The value may have moved since the proposal (another change approved in between).
            if approve and cfg is not None:
                now = SETTINGS[row["setting"]].read(apply(cfg, rows))
                if now != row["from"]:
                    raise PolicyError(f"{SETTINGS[row['setting']].label} has changed since this was proposed "
                                      f"(it is now {fmt(SETTINGS[row['setting']], now)}); propose it again", 409)
            row.update(status="approved" if approve else "withdrawn" if own else "rejected",
                       decided_by=who, decided_at=_now(), note=(str(note).strip()[:MAX_REASON] or None) if note else None)
            self._write(rows)
        return row

    def change(self, key, to, who, cfg: dict) -> dict:
        """A replay assumption, changed by the approver. Recorded as approved by them."""
        s = setting(key)
        if s.route != "direct":
            raise PolicyError(f"{s.label} needs a proposal and a second person's approval")
        if not who:
            raise PolicyError("say who is making the change")
        value = s.clean(to)
        with self._lock:
            rows = self._read()
            now = s.read(apply(cfg, rows))
            if value == now:
                raise PolicyError(f"{s.label} is already {fmt(s, now)}")
            stamp = _now()
            row = {"id": uuid.uuid4().hex[:12], "setting": key, "route": s.route, "from": now, "to": value,
                   "reason": None, "status": "approved", "proposed_by": who, "proposed_at": stamp,
                   "decided_by": who, "decided_at": stamp, "note": None}
            rows.append(row)
            self._write(rows)
        return row

    # ------------------------------------------------------------------ what the screen reads
    def state(self, cfg: dict, applied: dict) -> dict:
        """Every setting: as configured, as approved, as the running figures use it, and pending.

        `cfg` is the config file as written; `applied` the config the figures were computed on.
        """
        rows = self.records()
        eff = apply(cfg, rows)
        out = []
        for s in SETTINGS.values():
            approved = [r for r in rows if r["setting"] == s.key and r["status"] == "approved"]
            last = approved[-1] if approved else None
            value = s.read(eff)
            out.append({
                "key": s.key, "group": s.group, "label": s.label, "unit": s.unit, "help": s.help,
                "route": s.route, "lo": s.lo, "hi": s.hi,
                "configured": s.read(cfg), "value": value, "applied": s.read(applied),
                "awaiting_recompute": value != s.read(applied),
                "approved": {"by": last["decided_by"], "at": last["decided_at"],
                             "proposed_by": last["proposed_by"]} if last else None,
                "pending": next((r for r in rows if r["setting"] == s.key and r["status"] == "pending"), None),
            })
        labelled = [{**r, "label": SETTINGS[r["setting"]].label, "unit": SETTINGS[r["setting"]].unit}
                    for r in rows if r["setting"] in SETTINGS]
        return {"settings": out, "history": labelled[::-1][:HISTORY],
                "awaiting_recompute": any(x["awaiting_recompute"] for x in out)}


def fmt(s: Setting, v) -> str:
    if s.unit == "bool":
        return "yes" if v else "no"
    return f"{v:.1%}" if s.unit == "rate" else f"{v:.2f}×"


# --------------------------------------------------------------------------- impact
def assumption_impacts(full, inv, cfg: dict) -> dict:
    """What each replay assumption decides, on one product's whole file.

    For each switch: how many applicants a rule would decline differently if it were flipped,
    found by replaying with it flipped. For the approve-when-no-rule-catches rule: how many
    applicants no rule catches, which is who it decides.
    """
    from src.client_replay import replay
    n = int(len(full.df))
    caught = full.res.hits.any(axis=1).to_numpy() if full.res.hits.shape[1] else np.zeros(n, bool)
    out = {"applicants": n}
    for key in ("missing_value_matches", "include_inactive_rules"):
        s = SETTINGS[key]
        flipped = copy.deepcopy(cfg)
        flipped[s.path[0]][s.path[1]] = not s.read(cfg)
        res = replay(full.df, inv, flipped, frames=full.frames)
        other = res.hits.any(axis=1).to_numpy() if res.hits.shape[1] else np.zeros(n, bool)
        moved = int((caught != other).sum())
        out[key] = {"changed": moved, "share": round(moved / n, 4) if n else None,
                    "newly_declined": int((other & ~caught).sum()),
                    "newly_passed": int((caught & ~other).sum())}
    free = int((~caught).sum())
    out["no_rule_matched"] = {"applies": free, "share": round(free / n, 4) if n else None}
    return out
