import json
from pathlib import Path

from kavzi_trader.ui.message_schemas import UI_SERVER_MESSAGE_ADAPTER

# The frontend generates its TS types from this file; a test keeps it in sync.
UI_SCHEMA_PATH = Path("ui/web/src/generated/ui-schema.json")


def render_ui_schema() -> str:
    schema = UI_SERVER_MESSAGE_ADAPTER.json_schema(mode="serialization")
    schema["title"] = "UiServerMessage"
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"
