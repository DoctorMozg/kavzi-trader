from kavzi_trader.evals.case_selector import CaseSelector
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema
from tests.evals.eval_fixtures import btc_frame, case_at

BLOCKED = {"LOW", "EXTREME"}
_LABEL_ORDER = ["SHORT"] * 6 + ["LONG"] * 6 + ["NO_TRADE"] * 6
_REGIMES = ["LOW", "EXTREME", "NORMAL", "HIGH"]


def _dataset() -> list[EvalCaseSchema]:
    frame = btc_frame()
    return [
        case_at(
            frame,
            1000 + i,
            label=label,
            regime=_REGIMES[i % len(_REGIMES)],
        )
        for i, label in enumerate(_LABEL_ORDER)
    ]


class TestDryRun:
    def test_covers_every_label_and_a_scout_passing_regime(self) -> None:
        picked = CaseSelector.dry_run(_dataset(), BLOCKED)

        assert len(picked) == 5
        assert {c.label.value for c in picked} == {"LONG", "SHORT", "NO_TRADE"}
        assert any(c.regime not in BLOCKED for c in picked)

    def test_each_label_is_represented_by_a_passing_regime_case(self) -> None:
        picked = CaseSelector.dry_run(_dataset(), BLOCKED)

        by_label = {c.label.value: c for c in picked[:3]}
        assert all(c.regime not in BLOCKED for c in by_label.values())

    def test_is_deterministic_and_has_no_duplicates(self) -> None:
        first = CaseSelector.dry_run(_dataset(), BLOCKED)
        second = CaseSelector.dry_run(_dataset(), BLOCKED)

        assert [c.case_id for c in first] == [c.case_id for c in second]
        assert len({c.case_id for c in first}) == len(first)

    def test_small_pool_returns_what_exists(self) -> None:
        assert len(CaseSelector.dry_run(_dataset()[:2], BLOCKED)) == 2

    def test_pool_without_passing_regimes_still_fills_the_dry_run(self) -> None:
        blocked_only = [c for c in _dataset() if c.regime in BLOCKED]

        assert len(CaseSelector.dry_run(blocked_only, BLOCKED)) == 5


class TestDryRunReachingLlm:
    def test_prefers_cases_the_pre_pass_lets_through(self) -> None:
        cases = _dataset()
        reaching = {c.case_id for c in cases[3:15]}

        picked = CaseSelector.dry_run(cases, BLOCKED, reaching_llm=reaching)

        assert len(picked) == 5
        assert {c.case_id for c in picked} <= reaching

    def test_keeps_label_stratification_among_eligible_cases(self) -> None:
        cases = _dataset()
        reaching = {c.case_id for c in cases}

        picked = CaseSelector.dry_run(cases, BLOCKED, reaching_llm=reaching)

        assert {c.label.value for c in picked[:3]} == {"LONG", "SHORT", "NO_TRADE"}

    def test_falls_back_to_the_plain_pick_when_too_few_are_eligible(self) -> None:
        cases = _dataset()
        reaching = {c.case_id for c in cases[:4]}

        picked = CaseSelector.dry_run(cases, BLOCKED, reaching_llm=reaching)

        plain = CaseSelector.dry_run(cases, BLOCKED)
        assert [c.case_id for c in picked] == [c.case_id for c in plain]


class TestBalancedHead:
    def test_limit_mixes_labels_although_the_file_is_grouped(self) -> None:
        picked = CaseSelector.balanced_head(_dataset(), 6)

        assert sorted(c.label.value for c in picked) == [
            "LONG",
            "LONG",
            "NO_TRADE",
            "NO_TRADE",
            "SHORT",
            "SHORT",
        ]

    def test_limit_above_size_returns_everything(self) -> None:
        assert len(CaseSelector.balanced_head(_dataset(), 99)) == 18
