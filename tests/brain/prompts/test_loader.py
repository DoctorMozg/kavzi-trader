from kavzi_trader.brain.context.context_dicts import SystemPromptContextDict
from kavzi_trader.brain.prompts.loader import PromptLoader


def _make_system_prompt_context() -> SystemPromptContextDict:
    """Build a complete system prompt context for template rendering tests."""
    return SystemPromptContextDict(
        min_rr_ratio="2.0",
        drawdown_pause_percent="3.0",
        drawdown_close_all_percent="5.0",
        confluence_enter_min=6,
        volatility_low_threshold="-1.5",
        volatility_high_threshold="1.0",
        volatility_extreme_threshold="2.0",
        tier_1_min_confidence="0.65",
        tier_2_min_confidence="0.70",
        tier_3_min_confidence="0.85",
    )


def test_prompt_loader_renders_analyst_system_prompt() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    assert "CONFLUENCE SCORING" in rendered, "Expected risk framework."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."
    assert "ORDER FLOW INTERPRETATION" in rendered, "Expected order flow guide."


def test_analyst_prompt_has_no_volatility_penalty_instruction() -> None:
    """After Phase 4 the volatility penalty is applied by the router, not
    the LLM. The former per-prompt subtraction instructions must be gone.
    """
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    assert "VOLATILITY PENALTY" not in rendered
    assert "-1 confluence penalty" not in rendered
    assert "-3 confluence penalty" not in rendered


def test_risk_framework_is_condensed() -> None:
    """Risk framework used to repeat the 8-signal rubric verbatim. After
    compression the rendered block stays under ~1700 chars; if it regrows
    past 2500 the redundant rubric has slipped back in.
    """
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    # Capture roughly the risk_framework section: from its heading down
    # to the next top-level block heading.
    framework_start = rendered.index("CONFLUENCE SCORING (0-11 scale)")
    framework_end = rendered.index("VOLATILITY REGIMES", framework_start)
    framework_block = rendered[framework_start:framework_end]
    # Reject any regression that lets the old ~1000-char rubric come back.
    assert len(framework_block) < 1500


def test_analyst_prompt_has_breakout_override() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    assert "BREAKOUT OVERRIDE" in rendered, (
        "Expected breakout override rule in analyst trend assessment."
    )


def test_analyst_prompt_has_short_recovery_veto() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("analyst", context=context)
    assert "SHORT RECOVERY VETO" in rendered, (
        "Expected SHORT recovery veto rule in analyst trend assessment."
    )
    # Veto must mention both conditions (RSI and recovery from low).
    assert "RSI_14" in rendered
    assert "lowest low" in rendered


def test_prompt_loader_renders_trader_system_prompt() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("trader", context=context)
    assert "FUNDING COSTS" in rendered, "Expected funding costs guidance."
    assert "ACCOUNT STATE RULES" in rendered, "Expected account state rules."
    assert "VOLATILITY REGIMES" in rendered, "Expected volatility guide."


def test_trader_prompt_has_schema_examples() -> None:
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("trader", context=context)
    assert "SCHEMA EXAMPLES" in rendered, (
        "Expected SCHEMA EXAMPLES block with WAIT/LONG few-shot examples."
    )


def test_trader_prompt_has_output_contract() -> None:
    """WU-A: JSON-only hard rule must appear before DECISION FRAMEWORK."""
    loader = PromptLoader()
    context = _make_system_prompt_context()
    rendered = loader.render_system_prompt("trader", context=context)
    assert "OUTPUT CONTRACT" in rendered, (
        "Expected OUTPUT CONTRACT block guarding against preamble text."
    )
    contract_pos = rendered.index("OUTPUT CONTRACT")
    framework_pos = rendered.index("DECISION FRAMEWORK")
    schema_pos = rendered.index("SCHEMA EXAMPLES")
    # Contract must come BEFORE the framework so the model sees it first.
    assert contract_pos < framework_pos, (
        "OUTPUT CONTRACT must precede DECISION FRAMEWORK so the JSON-only"
        " rule is read before the reasoning framework."
    )
    assert contract_pos < schema_pos
