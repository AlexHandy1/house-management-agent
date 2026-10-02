from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from services import news_data_pull

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fake_response(text: str) -> MagicMock:
    response = MagicMock()
    response.text = text
    response.raise_for_status = lambda: None
    return response


def test_fetch_nrla_articles_excludes_articles_published_before_the_cutoff(monkeypatch):
    html = (FIXTURES_DIR / "nrla_news.html").read_text()
    monkeypatch.setattr(news_data_pull.requests, "get", lambda *a, **k: _fake_response(html))

    articles = news_data_pull.fetch_nrla_articles(cutoff=date(2026, 9, 1))

    [article] = articles
    assert article.source == "NRLA"
    assert article.title == "New rules for landlords"
    assert article.url == "https://www.nrla.org.uk/news/recent-article"
    assert article.published_date == date(2026, 9, 28)
    assert article.summary == "A summary of the new rules."


def test_fetch_tds_articles_excludes_articles_published_before_the_cutoff(monkeypatch):
    xml = (FIXTURES_DIR / "tds_sitemap.xml").read_text()
    monkeypatch.setattr(news_data_pull.requests, "get", lambda *a, **k: _fake_response(xml))

    articles = news_data_pull.fetch_tds_articles(cutoff=date(2026, 9, 1))

    [article] = articles
    assert article.source == "Tenancy Deposit Scheme"
    assert article.title == "recent article slug"
    assert article.url == "https://www.tenancydepositscheme.com/news/recent-article-slug"
    assert article.published_date == date(2026, 9, 28)
    assert article.summary is None
