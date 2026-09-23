import pytest

from services.agent import build_client, respond_to_issue


@pytest.mark.eval
def test_responds_to_a_leaking_boiler_report():
    reply = respond_to_issue("The boiler is leaking water onto the kitchen floor.", build_client())

    print(f"[eval] respond_to_issue\n  input='The boiler is leaking...'\n  output={reply!r}")
    assert reply
    assert "boiler" in reply.lower()
