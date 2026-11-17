"""Writes openapi.json (the contract the web app's types are generated from)."""
import json
from pathlib import Path

from app.main import app

Path(__file__).resolve().parent.parent.joinpath("openapi.json").write_text(
    json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
)
