from fastapi.testclient import TestClient

from main import create_app


def test_serves_index_html_at_root_when_static_dir_present(tmp_path):
    (tmp_path / "index.html").write_text("<h1>House Management Agent</h1>")

    app = create_app(static_dir=tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "House Management Agent" in response.text


def test_starts_without_static_dir_present(tmp_path):
    missing_dir = tmp_path / "does-not-exist"

    app = create_app(static_dir=missing_dir)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
