"""Offline scenario scoring — reads replay logs only, never the runtime path.

Design reference: plans/reports/plan.md §3.7. This module reads the
`scenario` ground-truth label to score detection precision/recall/lag. It
must import NOTHING from `trust/` or `agents/` (INV-9) — the label is not
allowed to leak back into the decision path through this module.

Input: a replay log — an iterable of records, each with at least
`{"epoch": int, "scenario": str, "detected": bool}`, where `detected` is
whatever the caller's own log already recorded as "did the system fire a
rule / invalidate an assumption / suspend a plan in this record" — this
module does not compute detection itself, only segments and scores it.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

NORMAL_SCENARIO = "NORMAL"


@dataclass
class ReplayRecord:
    epoch: int
    scenario: str
    detected: bool


@dataclass
class Segment:
    scenario: str
    start_epoch: int
    end_epoch: int
    records: list[ReplayRecord] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return any(r.detected for r in self.records)

    @property
    def detection_lag_s(self) -> int | None:
        if self.scenario == NORMAL_SCENARIO:
            return None
        for r in self.records:
            if r.detected:
                return r.epoch - self.start_epoch
        return None

    @property
    def false_alarm(self) -> bool:
        return self.scenario == NORMAL_SCENARIO and self.detected


def load_replay_log(path: str | Path) -> list[ReplayRecord]:
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            records.append(
                ReplayRecord(
                    epoch=int(row["epoch"]),
                    scenario=str(row["scenario"]),
                    detected=bool(row.get("detected", False)),
                )
            )
    return records


def segment(records: Iterable[ReplayRecord]) -> Iterator[Segment]:
    """Group consecutive records sharing the same `scenario` value."""
    current: Segment | None = None
    for r in sorted(records, key=lambda rec: rec.epoch):
        if current is None or r.scenario != current.scenario:
            if current is not None:
                yield current
            current = Segment(scenario=r.scenario, start_epoch=r.epoch, end_epoch=r.epoch)
        current.records.append(r)
        current.end_epoch = r.epoch
    if current is not None:
        yield current


@dataclass
class ScoreReport:
    segments: list[Segment]

    @property
    def incident_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.scenario != NORMAL_SCENARIO]

    @property
    def normal_segments(self) -> list[Segment]:
        return [s for s in self.segments if s.scenario == NORMAL_SCENARIO]

    @property
    def recall(self) -> float | None:
        incidents = self.incident_segments
        if not incidents:
            return None
        return sum(1 for s in incidents if s.detected) / len(incidents)

    @property
    def false_alarm_rate(self) -> float | None:
        normals = self.normal_segments
        if not normals:
            return None
        return sum(1 for s in normals if s.false_alarm) / len(normals)

    def to_dict(self) -> dict:
        return {
            "recall": self.recall,
            "false_alarm_rate": self.false_alarm_rate,
            "segments": [
                {
                    "scenario": s.scenario,
                    "start_epoch": s.start_epoch,
                    "end_epoch": s.end_epoch,
                    "detected": s.detected if s.scenario != NORMAL_SCENARIO else None,
                    "detection_lag_s": s.detection_lag_s,
                    "false_alarm": s.false_alarm if s.scenario == NORMAL_SCENARIO else None,
                }
                for s in self.segments
            ],
        }


def score(records: Iterable[ReplayRecord]) -> ScoreReport:
    return ScoreReport(segments=list(segment(records)))


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m eval.score_scenarios <replay_log.jsonl>", file=sys.stderr)
        sys.exit(2)
    records = load_replay_log(sys.argv[1])
    report = score(records)
    print(json.dumps(report.to_dict(), indent=2))


if __name__ == "__main__":
    main()
