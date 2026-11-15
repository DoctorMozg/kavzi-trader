---
name: filter-config-wiring
description: A pre-trade filter tunable is wired across three coordinated locations
metadata:
  type: project
---

A filter tunable in the spine filter chain is defined in three coordinated places that must stay in sync:

1. `kavzi_trader/spine/filters/config.py` — `FilterConfigSchema` field (`Annotated[int, Field(...)]`, frozen Pydantic model).
2. `config/config.yaml` under the `filters:` section — the runtime value override.
3. The filter class constructor (e.g. `kavzi_trader/spine/filters/fear_greed_gate.py`) — reads the field into a `self._...` attribute.

**Why:** Adding or removing one without the others leaves a dead field, an orphaned attribute, or an unread yaml key (a "ghost").
**How to apply:** When deleting a filter tunable, edit all three. After removal, check whether the constructor attribute (and any sibling threshold it paired with) is now unused and remove that too. Verify with a repo-wide grep over `--include="*.py" --include="*.yaml"`.
