import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from kavzi_trader.cli.commands.evals import eval_group
from kavzi_trader.config import AppConfig, SystemConfigSchema
from kavzi_trader.evals.case_dataset_file import CaseDatasetFile
from kavzi_trader.evals.result_store import ResultStore
from tests.evals.eval_fixtures import FakeLlmAgents, btc_frame, case_at, write_cache

_LABELS = ["SHORT", "LONG", "NO_TRADE"]
_REGIMES = ["NORMAL", "HIGH", "LOW", "EXTREME"]


@contextmanager
def _silenced_live_logs() -> Iterator[None]:
    """Pytest's log_cli handler resets sys.stdout on every record, which swallows
    everything CliRunner captures afterwards; mute it while the command runs."""
    handlers = [
        h
        for h in logging.getLogger().handlers
        if type(h).__name__ == "_LiveLoggingStreamHandler"
    ]
    levels = [h.level for h in handlers]
    for handler in handlers:
        handler.setLevel(logging.CRITICAL + 1)
    try:
        yield
    finally:
        for handler, level in zip(handlers, levels, strict=True):
            handler.setLevel(level)


class RunEnv:
    """A dataset of eight cases over one synthetic cache, plus a results dir."""

    def __init__(self, root: Path, app_config: AppConfig) -> None:
        frame = btc_frame()
        write_cache(root / "cache", frame)
        cases = [
            case_at(
                frame,
                1090 + i,
                label=_LABELS[i % 3],
                regime=_REGIMES[i % 4],
            )
            for i in range(8)
        ]
        self.dataset = root / "cases.jsonl"
        CaseDatasetFile(self.dataset).write(cases)
        self.case_ids = [c.case_id for c in cases]
        self.cache = root / "cache"
        self.results_dir = root / "results"
        self.config = app_config.model_copy(
            update={"system": SystemConfigSchema(results_dir=self.results_dir)}
        )
        self.agents = FakeLlmAgents(self.config)

    def invoke(self, *args: str, answer: str | None = None) -> Result:
        with _silenced_live_logs():
            return CliRunner().invoke(
                eval_group,
                [
                    "run",
                    "--dataset",
                    str(self.dataset),
                    "--cache-dir",
                    str(self.cache),
                    *args,
                ],
                obj={"app_config": self.config, "agent_source": self.agents},
                input=answer,
                standalone_mode=False,
            )

    def run_id(self, result: Result) -> str:
        match = re.search(r"Run (run_\w+):", result.output)
        assert match is not None, result.output
        return match.group(1)

    def store(self, run_id: str) -> ResultStore:
        return ResultStore(self.results_dir / "evals", run_id)


@pytest.fixture
def env(tmp_path: Path, app_config: AppConfig) -> RunEnv:
    return RunEnv(tmp_path, app_config)


def test_declining_after_dry_run_stops_with_the_dry_run_saved(env: RunEnv) -> None:
    result = env.invoke("--bypass-scout", answer="n\n")

    assert "Stopped after the dry run" in str(result.exception)
    assert "Dry run: 5 cases measured" in result.output
    assert "Remaining 3 cases" in result.output
    assert "Continue with the remaining cases?" in result.output
    assert len(env.store(env.run_id(result)).read_all()) == 5


def test_yes_skips_the_prompt_but_still_prints_the_dry_run(env: RunEnv) -> None:
    result = env.invoke("--bypass-scout", "--yes")

    assert result.exception is None
    assert "Dry run: 5 cases measured" in result.output
    assert "cost/case:" in result.output
    assert "latency/case:" in result.output
    assert "Continue" not in result.output
    assert "Finished 8 cases" in result.output
    done = env.store(env.run_id(result)).read_all()
    assert sorted(r.case_id for r in done) == sorted(env.case_ids)


def test_limit_five_runs_only_the_dry_run(env: RunEnv) -> None:
    result = env.invoke("--bypass-scout", "--limit", "5")

    assert result.exception is None
    assert "Continue" not in result.output
    assert len(env.store(env.run_id(result)).read_all()) == 5


def test_scout_skip_is_default_and_recorded(env: RunEnv) -> None:
    result = env.invoke("--cases", env.case_ids[2], "--yes")

    assert result.exception is None
    only = env.store(env.run_id(result)).read_all()[0]
    assert only.regime == "LOW"
    assert only.scout_verdict == "SKIP"
    assert only.stopped_at == "scout"
    assert not only.scout_bypassed
    assert env.agents.calls == {"analyst": 0, "trader": 0}


def test_resume_does_not_repeat_finished_cases(env: RunEnv) -> None:
    first = env.invoke("--bypass-scout", answer="n\n")
    run_id = env.run_id(first)

    second = env.invoke("--bypass-scout", "--resume", run_id, "--yes")

    assert second.exception is None
    assert "3 cases to run, 5 already done" in second.output
    ids = [r.case_id for r in env.store(run_id).read_all()]
    assert sorted(ids) == sorted(env.case_ids)


def test_resume_with_a_different_setup_is_refused(env: RunEnv) -> None:
    first = env.invoke("--bypass-scout", answer="n\n")

    second = env.invoke("--resume", env.run_id(first), "--yes")

    assert "bypass_scout" in str(second.exception)


def test_header_records_the_run_config(env: RunEnv) -> None:
    result = env.invoke("--bypass-scout", "--limit", "5")

    header = env.store(env.run_id(result)).read_header()
    assert header.bypass_scout
    assert header.concurrency == 4
    assert header.provider == "anthropic"


def test_unknown_case_id_is_rejected(env: RunEnv) -> None:
    result = env.invoke("--cases", "nope")

    assert "Unknown case ids: nope" in str(result.exception)


def test_missing_api_key_is_reported_without_a_run(
    tmp_path: Path, app_config: AppConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KT_ANTHROPIC_API_KEY", raising=False)
    env = RunEnv(tmp_path, AppConfig.from_env())

    result = CliRunner().invoke(
        eval_group,
        ["run", "--dataset", str(env.dataset), "--cache-dir", str(env.cache)],
        obj={"app_config": env.config},
        standalone_mode=False,
    )

    assert "KT_ANTHROPIC_API_KEY" in str(result.exception)
    assert not env.results_dir.exists()
