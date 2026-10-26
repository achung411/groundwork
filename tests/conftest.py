import pytest

from app.db import connect, initialize
from app.seed import seed


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setenv("PROPERTY_DB_PATH", str(path))
    initialize()
    with connect() as connection:
        seed(connection)
    return path
