"""eval/score_scenarios.py — segment, detect, false-alarm. plans/reports/
plan.md §3.7, phase-06 success criteria (no import from trust/ or agents/).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from eval.score_scenarios import ReplayRecord, score

EVAL_MODULE = Path(__file__).resolve().parents[2] / "eval" / "score_scenarios.py"


@pytest.mark.data_plane
def test_no_trust_or_agents_import_anywhere_in_module():
    tree = ast.parse(EVAL_MODULE.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert "trust" not in imported
    assert "agents" not in imported


@pytest.mark.data_plane
def test_segment_and_score_normal_only_no_false_alarm():
    records = [ReplayRecord(epoch=i, scenario="NORMAL", detected=False) for i in range(5)]
    report = score(records)
    assert len(report.segments) == 1
    assert report.false_alarm_rate == 0.0
    assert report.recall is None


@pytest.mark.data_plane
def test_incident_segment_detected_with_lag():
    records = [
        ReplayRecord(epoch=0, scenario="NORMAL", detected=False),
        ReplayRecord(epoch=10, scenario="PUMP_FAULT", detected=False),
        ReplayRecord(epoch=20, scenario="PUMP_FAULT", detected=True),
        ReplayRecord(epoch=30, scenario="PUMP_FAULT", detected=False),
        ReplayRecord(epoch=40, scenario="NORMAL", detected=False),
    ]
    report = score(records)
    incident = report.incident_segments[0]
    assert incident.detected is True
    assert incident.detection_lag_s == 10
    assert report.recall == 1.0


@pytest.mark.data_plane
def test_false_alarm_on_normal_segment():
    records = [
        ReplayRecord(epoch=0, scenario="NORMAL", detected=False),
        ReplayRecord(epoch=10, scenario="NORMAL", detected=True),
    ]
    report = score(records)
    assert report.false_alarm_rate == 1.0
