from datetime import date

from jobs import pull_news_feed
from models.article import Article
from services import articles_table


def _article(source: str, slug: str, published: date) -> Article:
    return Article(
        source=source,
        title=slug.replace("-", " "),
        url=f"https://example.com/news/{slug}",
        published_date=published,
    )


def test_a_run_where_both_sources_succeed_saves_articles_from_both(
    articles_database_url, monkeypatch
):
    monkeypatch.setattr(
        pull_news_feed.news_data_pull,
        "fetch_nrla_articles",
        lambda cutoff: [_article("NRLA", "nrla-article", date(2026, 9, 28))],
    )
    monkeypatch.setattr(
        pull_news_feed.news_data_pull,
        "fetch_tds_articles",
        lambda cutoff: [_article("Tenancy Deposit Scheme", "tds-article", date(2026, 9, 27))],
    )

    succeeded = pull_news_feed.run(lookback_days=2)

    assert succeeded is True
    saved_titles = {a["title"] for a in articles_table.list_recent_articles()}
    assert saved_titles == {"nrla article", "tds article"}


def test_a_run_where_one_source_fails_still_saves_the_other_sources_articles(
    articles_database_url, monkeypatch
):
    def _raise(cutoff: date) -> list[Article]:
        raise RuntimeError("NRLA is down")

    monkeypatch.setattr(pull_news_feed.news_data_pull, "fetch_nrla_articles", _raise)
    monkeypatch.setattr(
        pull_news_feed.news_data_pull,
        "fetch_tds_articles",
        lambda cutoff: [_article("Tenancy Deposit Scheme", "tds-article", date(2026, 9, 27))],
    )

    succeeded = pull_news_feed.run(lookback_days=2)

    assert succeeded is False
    [saved] = articles_table.list_recent_articles()
    assert saved["title"] == "tds article"
