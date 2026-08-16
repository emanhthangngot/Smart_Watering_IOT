---
phase: 1
title: "Skeleton and config"
status: completed
priority: P1
effort: "1h"
dependencies: []
---

# Phase 1: Skeleton and config

## Overview

Seed every owned directory on `dev` before any branch exists, so no branch
ever creates a top-level directory and no two branches can invent
conflicting layouts for the same concern (`plan.md` §2).

## Requirements

- Functional: every directory in the ownership table exists with an
  `__init__.py` (Python packages) and a `README.md` naming its owner and
  the `plan.md` section it implements.
- Non-functional: `make check` runs clean on the empty skeleton (ruff, pytest
  collect zero failures).

## Architecture

- `api/main.py` auto-discovers `api/routers/*.py` — no shared router
  registration list, kills the classic FastAPI merge conflict.
- `trust/rules/` is one file per rule (populated in M2's phase-02) —
  discovered by a registry function, never a shared list literal.
- `tests/invariants/` is one file per invariant (INV-1..INV-10), owned by
  whoever owns that invariant's module.
- `requirements/<role>.txt` — one file per owner, `requirements/base.txt`
  is dev-owned shared pins.
- `.env.example` — owner-tagged append-only blocks.
- `store/schema.sql` will be generated (`store/gen_ddl.py`) in M1's
  phase-02, never hand-edited — kills the 6-table schema-drift risk in
  `plan.md` §16.

## Related Code Files

- Create: `contracts.py`, `config.py`, `pyproject.toml`, `Makefile`,
  `.editorconfig`, `.gitignore`, `api/main.py`, `.env.example`,
  `CODEOWNERS`, `.github/pull_request_template.md`,
  `scripts/check-ownership.sh`, `requirements/*.txt`
- Create: `registry/ ingest/ sim/ store/ eval/ fixtures/ trust/ trust/rules/
  worldstate/ agents/ graph/ prompts/ tools/ schedule/ verify/ api/
  api/routers/ frontend/ tests/{data_plane,trust,agents,tools,invariants}/`
  (each with `__init__.py` + `README.md`)

## Implementation Steps

1. `git checkout -b dev main`
2. Create all directories, `__init__.py` for Python packages.
3. Write owner `README.md` per directory (owner + `plan.md` section ref).
4. Write `contracts.py`/`config.py` stubs, `pyproject.toml`, `Makefile`.
5. Write `api/main.py` with router auto-discovery.
6. Write `.env.example`, `.gitignore`, `.editorconfig`.
7. Write `CODEOWNERS` from the owner table.
8. Write `scripts/check-ownership.sh`, `chmod +x`.
9. Write `requirements/base.txt` + one file per owner.
10. Commit.

## Success Criteria

- [x] `find . -maxdepth 3 -name README.md` lists all 20 owned directories.
- [x] `git log --oneline dev` shows one seed commit.
- [ ] `make check` passes on `dev` HEAD (deferred — no deps installed in
      this environment; owners run this on first PR).
- [x] `bash scripts/check-ownership.sh` script exists and is executable.

## Risk Assessment

Empty skeleton risk: a stub can drift from what M1 actually needs by G0.
Mitigation: `contracts.py`/`config.py` are explicitly marked STATUS: stub,
owned by M1 from phase-01 onward — dev's version is a placeholder that M1
overwrites, not a contract dev locks in.
