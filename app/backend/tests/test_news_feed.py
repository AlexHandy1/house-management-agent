from datetime import date

from fastapi.testclient import TestClient

from main import app
from models.article import Article
from services import articles_table

client = TestClient(app)


def test_getting_the_news_feed_returns_saved_articles_newest_first(articles_database_url):
    articles_table.save_articles(
        [
            Article(
                source="NRLA",
                title="Older article",
                url="https://www.nrla.org.uk/news/older",
                published_date=date(2026, 9, 1),
                summary="Older news.",
            ),
            Article(
                source="Tenancy Deposit Scheme",
                title="newer article",
                url="https://www.tenancydepositscheme.com/news/newer",
                published_date=date(2026, 9, 28),
            ),
        ]
    )

    response = client.get("/api/news-feed")

    assert response.status_code == 200
    body = response.json()
    assert [article["title"] for article in body] == ["newer article", "Older article"]
    assert body[0]["source"] == "Tenancy Deposit Scheme"
    assert body[0]["summary"] is None
