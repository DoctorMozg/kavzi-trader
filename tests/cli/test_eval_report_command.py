from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig, SystemConfigSchema
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.result_store import ResultStore
from kavzi_trader.evals.run_header_schema import RunHeaderSchema
from tests.cli.test_eval_run_command import _silenced_live_logs
from tests.evals.eval_fixtures import write_cache
from tests.evals.report_fixtures import (
    case_for,
    flat_frame,
    joined,
    trader_record,
)

RUN_ID = "run_test"


class ReportEnv:
    """A two-case run: one LONG trade that hits TP, one scout skip."""

    def __init__(self, root: Path, app_config: AppConfig) -> None:
        frame = flat_frame()
        frame.loc[12, "high"] = 104.5
        write_cache(root / "cache", frame)
        trade_case = case_for(frame, "LONG")
        skip_case = case_for(frame, "NO_TRADE", case_id="BTCUSDT-skip")
        self.dataset = root / "cases.jsonl"
        CaseDatasetFile(self.dataset).write([trade_case, skip_case])
        self.results_dir = root / "results"
        store = ResultStore(self.results_dir / "evals", RUN_ID)
        store.write_header(
            RunHeaderSchema(
                run_id=RUN_ID,
                dataset=str(self.dataset),
                analyst_model="a",
                analyst_effort="low",
                trader_model="t",
                trader_effort="low",
                provider="p",
                bypass_scout=False,
                concurrency=2,
            )
        )
        for entry in (
            joined(trade_case, "trader", trader_record("LONG")),
            joined(skip_case, "scout"),
        ):
            store.append(entry.result)
        self.cache = root / "cache"
        self.config = app_config.model_copy(
            update={"system": SystemConfigSchema(results_dir=self.results_dir)}
        )

    def invoke(self, *args: str) -> Result:
        with _silenced_live_logs():
            return CliRunner().invoke(
                eval_group,
                ["report", "--cache-dir", str(self.cache), *args],
                obj={"app_config": self.config},
                standalone_mode=False,
            )


@pytest.fixture
def env(tmp_path: Path, app_config: AppConfig) -> ReportEnv:
    return ReportEnv(tmp_path, app_config)


def test_report_is_written_next_to_the_results_and_summarised(env: ReportEnv) -> None:
    result = env.invoke("--run", RUN_ID)

    assert result.exception is None
    path = env.results_dir / "evals" / f"{RUN_ID}.report.md"
    assert f"Report: {path}" in result.output
    assert "Cases: 2 scored, 0 errored" in result.output
    assert "Accuracy 1.000" in result.output
    assert "Simulated: 1 trades, mean R 2.00, total R 2.00" in result.output
    text = path.read_text(encoding="utf-8")
    for heading in ("## Run", "## Pipeline funnel", "## Simulated outcome", "## Ops"):
        assert heading in text
    assert "| LONG | 1 | 0 | 0 |" in text


def test_out_overrides_the_report_path(env: ReportEnv, tmp_path: Path) -> None:
    target = tmp_path / "elsewhere" / "r.md"

    result = env.invoke("--run", RUN_ID, "--out", str(target))

    assert result.exception is None
    assert target.exists()


def test_unknown_run_names_the_missing_header(env: ReportEnv) -> None:
    result = env.invoke("--run", "run_nope")

    assert isinstance(result.exception, FileNotFoundError)
    assert "run_nope.header.json" in str(result.exception)
