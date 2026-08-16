"""INV-9: the literal string `scenario` never appears in trust/, agents/,
graph/ source — the ground-truth label must never leak into the decision
path. plans/reports/plan.md §3.7, §12.

Owner: shared / append-only (tests/invariants/), enforcement mechanism
authored by M1 feat/data-plane, phase-06 (eval/score_scenarios.py isolation).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.invariants

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED_DIRS = ("trust", "agents", "graph")


def _python_files(directory: Path):
    if not directory.exists():
        return
    yield from directory.rglob("*.py")


def test_scenario_literal_absent_from_guarded_dirs():
    violations = []
    for dirname in GUARDED_DIRS:
        for path in _python_files(REPO_ROOT / dirname):
            text = path.read_text()
            if "scenario" in text:
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if "scenario" in line:
                        violations.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not violations, "INV-9 violated — 'scenario' found in:\n" + "\n".join(violations)
