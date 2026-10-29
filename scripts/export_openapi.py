"""Write the standing API's OpenAPI document to docs/openapi.json.

tests/test_api.py fails when the committed file and the code disagree, so run
this (``make openapi``) after changing any endpoint or response model.
"""

from __future__ import annotations

import json
from pathlib import Path

from clinician_standing.api.app import create_app
from clinician_standing.api.auth import ApiSettings
from clinician_standing.api.store import MemoryStore

OUT = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def main() -> None:
    app = create_app(
        store=MemoryStore([], []),
        settings=ApiSettings(database_url=None, api_keys=()),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
