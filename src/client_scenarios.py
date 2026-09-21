"""Saved scenarios: named, attributed, and re-run by the engine rather than trusted (TODO B4).

A scenario is the steps a person built in the Simulator plus the context they built it in
(product and analysis window). Saving one re-runs it here, so the stored outcome is the engine's
and not whatever the page last showed. Comparing re-runs each one again in its own context, and
says when the answer has moved since it was saved (new data, a new rule pack).

Every save and delete is recorded with who and when. A deleted scenario is kept, marked deleted,
so the record of what was proposed survives. Until the server authenticates people, `who` is the
name the page sends; the field is where the ABAC identity goes.

The store is one JSON file (config `scenarios.path`), written whole under a lock. It suits a
single bank's analytics team; a deployment with many writers moves it to the database.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_NAME = 80

# The outcome figures a saved scenario keeps. The page compares these; it computes none of them.
OUTCOME_KEYS = ("approval_rate", "approval_rate_before", "approval_change_pp", "booked_after",
                "swap_in", "swap_out", "expected_bad_rate", "risk_known",
                "booked_bad_rate_before", "swap_out_observed_bad_rate", "verdict", "direction")


class ScenarioError(ValueError):
    """A save, delete or compare the store refuses. The message says why, in words."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def outcome(result: dict) -> dict:
    return {k: result.get(k) for k in OUTCOME_KEYS}


def drift(saved: dict, now: dict) -> list[str]:
    """What has moved between the outcome at save time and a fresh re-run, in words."""
    out = []
    if saved.get("approval_rate") != now.get("approval_rate"):
        out.append("approval rate")
    if saved.get("risk_known") != now.get("risk_known") or \
            saved.get("expected_bad_rate") != now.get("expected_bad_rate"):
        out.append("bad rate")
    if saved.get("swap_in") != now.get("swap_in") or saved.get("swap_out") != now.get("swap_out"):
        out.append("who moves")
    return out


class ScenarioStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ScenarioError(f"the scenario file {self.path.name} is damaged: {e}", 500) from None
        return data.get("scenarios", []) if isinstance(data, dict) else []

    def _write(self, rows: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"scenarios": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)                  # never a half-written file

    def list(self, product: str | None = None) -> list[dict]:
        with self._lock:
            rows = [r for r in self._read() if not r.get("deleted_at")]
        if product:
            rows = [r for r in rows if r["product"] == product]
        return sorted(rows, key=lambda r: r["saved_at"], reverse=True)

    def get(self, sid: str) -> dict:
        with self._lock:
            for r in self._read():
                if r["id"] == sid and not r.get("deleted_at"):
                    return r
        raise ScenarioError(f"no saved scenario {sid!r}", 404)

    def add(self, record: dict) -> dict:
        name = str(record.get("name") or "").strip()
        if not name:
            raise ScenarioError("give the scenario a name")
        if len(name) > MAX_NAME:
            raise ScenarioError(f"a scenario name is at most {MAX_NAME} characters")
        with self._lock:
            rows = self._read()
            live = [r for r in rows if not r.get("deleted_at") and r["product"] == record["product"]]
            same = next((r for r in live if r["name"].casefold() == name.casefold()), None)
            if same:
                raise ScenarioError(f"a {record['product']} scenario is already called “{same['name']}”", 409)
            row = {**record, "name": name, "id": uuid.uuid4().hex[:12], "saved_at": _now()}
            rows.append(row)
            self._write(rows)
        return row

    def delete(self, sid: str, who: str) -> dict:
        with self._lock:
            rows = self._read()
            for r in rows:
                if r["id"] == sid and not r.get("deleted_at"):
                    r["deleted_at"], r["deleted_by"] = _now(), who or None
                    self._write(rows)
                    return r
        raise ScenarioError(f"no saved scenario {sid!r}", 404)
