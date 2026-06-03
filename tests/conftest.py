import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dava.db import Database


@pytest.fixture
def tmp_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def db(tmp_data_dir):
    db_path = tmp_data_dir / "test.db"
    database = Database(str(db_path), str(tmp_data_dir), admin_ids={111, 222})
    yield database
    database._conn.close()


@pytest.fixture
def db_with_user(db):
    db.ensure_user(1)
    return db


@pytest.fixture
def db_with_allowed_user(db):
    db.grant(1)
    return db


@pytest.fixture
def mock_config(tmp_path):
    config = MagicMock()
    config.bot_token = "test-bot-token"
    config.api_id = "12345"
    config.api_hash = "test-api-hash"
    config.polza_api_key = "test-polza-key"
    config.cookies = "test-cookies"
    config.admin_chat_ids = [111]
    config.data_dir = str(tmp_path / "data")
    config._hidden = {"bot_token", "api_id", "api_hash", "polza_api_key", "cookies"}
    return config


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client