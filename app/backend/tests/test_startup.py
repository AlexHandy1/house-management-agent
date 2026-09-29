from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app
from services import issues_db


def test_the_issues_schema_is_initialised_on_startup(monkeypatch):
    init_schema = MagicMock()
    monkeypatch.setattr(issues_db, "init_schema", init_schema)

    with TestClient(app):
        pass

    init_schema.assert_called_once_with()
