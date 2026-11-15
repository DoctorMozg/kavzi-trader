import logging
from collections.abc import Collection

from kavzi_trader.evals.barrier_enums import CaseLabel
from kavzi_trader.evals.eval_case_schema import EvalCaseSchema

logger = logging.getLogger(__name__)

DRY_RUN_SIZE = 5


class CaseSelector:
    """Deterministic picks: a label-balanced subset and the stratified dry run."""

    @staticmethod
    def balanced_head(cases: list[EvalCaseSchema], limit: int) -> list[EvalCaseSchema]:
        """First ``limit`` cases, taking labels round-robin in dataset order.

        The dataset file is grouped by label, so a plain head would be one-sided.
        """
        queues = {label: [c for c in cases if c.label is label] for label in CaseLabel}
        picked: list[EvalCaseSchema] = []
        while len(picked) < min(limit, len(cases)):
            for queue in queues.values():
                if queue and len(picked) < limit:
                    picked.append(queue.pop(0))
        return picked

    @classmethod
    def dry_run(
        cls,
        cases: list[EvalCaseSchema],
        blocked_regimes: Collection[str],
        size: int = DRY_RUN_SIZE,
        *,
        reaching_llm: Collection[str] | None = None,
    ) -> list[EvalCaseSchema]:
        """Stratified pick from ``reaching_llm`` ids (the pre-pass), if at least
        ``size`` of them exist; otherwise from all cases."""
        if reaching_llm is not None:
            eligible = [c for c in cases if c.case_id in reaching_llm]
            if len(eligible) >= size:
                return cls._stratified(eligible, (), size)
            logger.warning(
                "Only %d of %d cases reach the Analyst LLM; dry run is not LLM-only",
                len(eligible),
                len(cases),
            )
        return cls._stratified(cases, blocked_regimes, size)

    @staticmethod
    def _stratified(
        cases: list[EvalCaseSchema], blocked_regimes: Collection[str], size: int
    ) -> list[EvalCaseSchema]:
        """One case per label from a regime Scout lets through, then new regimes."""
        chosen: list[EvalCaseSchema] = []
        for label in CaseLabel:
            match = next(
                (
                    c
                    for c in cases
                    if c.label is label and c.regime not in blocked_regimes
                ),
                None,
            )
            if match is not None:
                chosen.append(match)
        if not chosen:
            logger.warning("No case in a Scout-passing regime for the dry run")
        remaining = [c for c in cases if c not in chosen]
        while remaining and len(chosen) < size:
            seen = {c.regime for c in chosen}
            pick = next((c for c in remaining if c.regime not in seen), remaining[0])
            chosen.append(pick)
            remaining.remove(pick)
        return chosen[:size]
