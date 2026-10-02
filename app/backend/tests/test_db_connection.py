from unittest.mock import MagicMock

from services import db_connection


def test_the_database_url_is_assembled_from_secret_manager_on_a_cloud_run_service(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "house-management-agent")
    monkeypatch.setenv("DB_HOST", "10.20.0.2")
    monkeypatch.setenv("DB_NAME", "house_mgmt")
    monkeypatch.setenv("DB_USER", "house_mgmt_app")
    monkeypatch.setattr(
        db_connection.google.auth, "default", lambda: (None, "house-management-agent")
    )
    fake_secret_client = MagicMock()
    fake_secret_client.access_secret_version.return_value = MagicMock(
        payload=MagicMock(data=b"s3cret-pw")
    )
    monkeypatch.setattr(
        db_connection.secretmanager, "SecretManagerServiceClient", lambda: fake_secret_client
    )

    url = db_connection.get_database_url()

    assert url == "postgresql://house_mgmt_app:s3cret-pw@10.20.0.2/house_mgmt"
    fake_secret_client.access_secret_version.assert_called_once_with(
        request={
            "name": "projects/house-management-agent/secrets/DATABASE_PASSWORD/versions/latest"
        }
    )


def test_the_database_url_is_assembled_from_secret_manager_on_a_cloud_run_job(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.setenv("CLOUD_RUN_JOB", "news-feed-pull")
    monkeypatch.setenv("DB_HOST", "10.20.0.2")
    monkeypatch.setenv("DB_NAME", "house_mgmt")
    monkeypatch.setenv("DB_USER", "house_mgmt_app")
    monkeypatch.setattr(
        db_connection.google.auth, "default", lambda: (None, "house-management-agent")
    )
    fake_secret_client = MagicMock()
    fake_secret_client.access_secret_version.return_value = MagicMock(
        payload=MagicMock(data=b"s3cret-pw")
    )
    monkeypatch.setattr(
        db_connection.secretmanager, "SecretManagerServiceClient", lambda: fake_secret_client
    )

    url = db_connection.get_database_url()

    assert url == "postgresql://house_mgmt_app:s3cret-pw@10.20.0.2/house_mgmt"
