# Trust engine (M2)

The trust package implements `plans/reports/plan.md` §§3.3, 3.5, 4, 5 and 10.3.
It consumes the frozen M1 registry and F1–F4 fixtures without copying them.

G2 fixture replay remains blocked until G0 lands `registry/specs.py` and those fixtures on `dev`.

## G2 status after data-plane merge

G0/G1 and F1-F4 landed on `dev` in PR #8. The trust engine now consumes the frozen
`MetricSpec` registry directly; the G2 replay passes all four fixtures.
