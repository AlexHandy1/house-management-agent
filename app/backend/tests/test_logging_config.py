import logging

import main  # noqa: F401  (import triggers app-level logging configuration)


def test_info_level_logs_are_not_silently_dropped():
    # Regression test: without configuring the root logger, Python defaults
    # to WARNING, so every logger.info(...) call in the app (route-triggered
    # logging, IAP identity logging) is silently dropped before it ever
    # reaches stdout/Cloud Logging — confirmed happening in a real deploy.
    # caplog-based tests don't catch this because caplog's own fixture
    # temporarily forces the level down during the test.
    assert logging.getLogger("routers.issue").isEnabledFor(logging.INFO)
