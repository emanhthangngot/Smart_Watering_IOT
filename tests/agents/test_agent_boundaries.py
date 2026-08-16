import ast
from pathlib import Path

import pytest

from agents.vocabulary import InteractionVerb

pytestmark = pytest.mark.agents


def test_vocabulary_is_exactly_six_verbs() -> None:
    assert {verb.value for verb in InteractionVerb} == {
        "PROPOSE",
        "ACCEPT",
        "REJECT",
        "REQUEST_MORE_EVIDENCE",
        "REVISE",
        "ESCALATE_TO_HUMAN",
    }


_M3_MODULES = (
    "agents/allocator.py",
    "agents/coordinator.py",
    "agents/messages.py",
    "agents/monitor.py",
    "agents/planner.py",
    "agents/resource.py",
    "agents/vocabulary.py",
    "graph/edges.py",
    "graph/explain.py",
    "graph/grounding.py",
    "worldstate/state.py",
    "worldstate/llm_slice.py",
)


def test_m3_modules_have_no_runtime_owner_imports() -> None:
    forbidden = {"tools", "schedule", "verify", "api", "store", "trust"}
    for filename in _M3_MODULES:
        tree = ast.parse(Path(filename).read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not imported & forbidden, f"{filename} imports forbidden module(s)"
