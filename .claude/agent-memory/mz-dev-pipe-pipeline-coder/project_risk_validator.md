---
name: project-risk-validator
description: Structure and conventions for DynamicRiskValidator checks in spine/risk/validator.py
metadata:
  type: project
---

`DynamicRiskValidator.validate_trade()` runs a sequence of independent checks, each appending to a shared `rejection_reasons: list[str]`. The trade is valid iff that list is empty.

Per-check conventions in `kavzi_trader/spine/risk/validator.py`:
- Single-reason checks return `str | None` (None = pass); caller does `if result: rejection_reasons.append(result)` then `logger.debug("X check: result=%s", result)`.
- Multi-reason checks return `list[str]` and the caller `.extend()`s.
- Checks that fetch from `state_manager` (Redis-backed) MUST fail-closed: wrap the fetch in try/except, `logger.exception(...)` with `extra={"reason": "risk_validation_error", "check": "<name>"}`, and return a rejection string so a state outage blocks trading rather than waving it through.
- Checks depending on `self._tier_registry` return `None` early when it is None (most unit tests construct `DynamicRiskValidator()` with no registry and must stay green). In production, `cli/commands/trade.py` injects the registry (loaded from `config/tiers.yaml`), so the check is live.

Per-symbol risk budgets live in `config/tiers.yaml` via `SymbolTierConfigSchema.risk_per_trade_percent` (TIER_1=4%, TIER_2=3%, TIER_3=2%). `RiskConfigSchema` enforces `drawdown_pause_percent < drawdown_close_all_percent` — a test config raising pause must also raise close-all.

**Why:** Two TIER_1 positions at 4% each = 8% aggregate open risk vs a 5% drawdown-pause; per-position caps don't bound aggregate single-candle loss. Portfolio-risk cap is derived as `drawdown_pause_percent - 0.5` (no new config key).
**How to apply:** When adding a new risk gate, copy the fail-closed + None-guard pattern of `_check_exposure`/`_check_total_portfolio_risk`, use `Decimal` arithmetic (never float), and wire it into `validate_trade()` in sequence.
