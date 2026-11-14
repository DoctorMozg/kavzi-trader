from pathlib import Path

from kavzi_trader.ui.schema_export import UI_SCHEMA_PATH, render_ui_schema

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_committed_frontend_schema_matches_models() -> None:
    committed = (REPO_ROOT / UI_SCHEMA_PATH).read_text(encoding="utf-8")

    assert committed == render_ui_schema(), (
        "UI schema drifted: run `uv run kavzitrader ui export-schema` and "
        "`npm run gen:types` in ui/web"
    )
