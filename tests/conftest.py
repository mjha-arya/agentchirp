import json
from pathlib import Path

import pytest

from agentchirp import config

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_payload() -> dict:
    return json.loads((FIXTURES / "x-sample.json").read_text(encoding="utf-8"))


@pytest.fixture
def light_payload() -> dict:
    return json.loads((FIXTURES / "x-light.json").read_text(encoding="utf-8"))


@pytest.fixture
def temp_data(tmp_path, monkeypatch) -> Path:
    """Point every data/ path at a throwaway directory."""
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    config.ensure_dirs()
    return config.DATA
