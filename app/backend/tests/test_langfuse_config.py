from services import langfuse_config


def test_a_secret_manager_failure_does_not_crash_app_startup(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "house-management-agent")

    def raise_fetch_error(secret_id):
        raise RuntimeError("Secret Manager unavailable")

    monkeypatch.setattr(langfuse_config, "_fetch_secret", raise_fetch_error)

    langfuse_config.configure()  # must not raise
