---
name: confluence-override-contract
description: get_confluence_override returns int|None and callers gate on None
metadata:
  type: project
---

`get_confluence_override(direction: str) -> int | None` is a Protocol method (declared in `brain/agent/analyst_pipeline.py` and `brain/agent/router.py`, implemented by `spine/filters/fear_greed_gate.py`). The caller in `analyst_pipeline.py` does `if override is not None: confluence_gate = max(confluence_gate, override)` — an override can only tighten the gate, never loosen it.

**Why:** Returning `None` for a branch is behavior-safe because the caller falls back to the regime default. A branch that returned `max(default, X)` where X <= the always-applied minimum confluence gate (NORMAL>=6, LOW/HIGH>=7, EXTREME>=8 from `brain/confluence_thresholds.py`) was mathematically inert and safely removable.
**How to apply:** When changing this method's branches, keep the `int | None` signature so both Protocol decls and the caller stay valid. To check if a branch is live, compare its returned threshold against the regime confluence floors — if it can never exceed them, it cannot reject and is dead.
