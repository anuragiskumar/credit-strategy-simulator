"""Runs the JavaScript unit tests for the shared funnel model (ui/tests/*.test.js).

They use Node's built-in test runner, so there is nothing to install; the test is skipped on a
machine without Node rather than failing.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

UI = Path(__file__).resolve().parent.parent / "ui"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.skipif(not (UI / "client_fixture.json").exists(), reason="fixture not built")
def test_funnel_model_js_unit_tests():
    files = sorted(str(p) for p in (UI / "tests").glob("*.test.js"))
    assert files, "no JS unit tests found"
    run = subprocess.run(["node", "--test", *files], capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stdout + run.stderr
