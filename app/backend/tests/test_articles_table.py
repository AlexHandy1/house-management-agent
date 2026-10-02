from datetime import date

from models.article import Article
from services import articles_table


def test_a_saved_article_can_be_listed_back(articles_database_url):
    article = Article(
        source="NRLA",
        title="New rules for landlords",
        url="https://www.nrla.org.uk/news/new-rules-for-landlords",
        published_date=date(2026, 9, 28),
        summary="A summary of the new rules.",
    )

    articles_table.save_articles([article])

    [saved] = articles_table.list_recent_articles()
    assert saved["source"] == "NRLA"
    assert saved["title"] == "New rules for landlords"
    assert saved["url"] == "https://www.nrla.org.uk/news/new-rules-for-landlords"
    assert saved["published_date"] == date(2026, 9, 28)
    assert saved["summary"] == "A summary of the new rules."


def test_saving_the_same_article_url_twice_does_not_duplicate_it(articles_database_url):
    article = Article(
        source="NRLA",
        title="New rules for landlords",
        url="https://www.nrla.org.uk/news/new-rules-for-landlords",
        published_date=date(2026, 9, 28),
        summary="Original summary.",
    )
    republished = article.model_copy(update={"summary": "Edited summary."})

    first_run_inserted = articles_table.save_articles([article])
    second_run_inserted = articles_table.save_articles([republished])

    assert first_run_inserted == 1
    assert second_run_inserted == 0
    [saved] = articles_table.list_recent_articles()
    assert saved["summary"] == "Original summary."


def test_listing_returns_only_the_requested_number_of_articles_newest_first(
    articles_database_url,
):
    articles = [
        Article(
            source="NRLA",
            title=f"Article {day}",
            url=f"https://www.nrla.org.uk/news/article-{day}",
            published_date=date(2026, 9, day),
        )
        for day in (10, 20, 15)
    ]

    articles_table.save_articles(articles)

    [first, second] = articles_table.list_recent_articles(limit=2)
    assert (first["title"], second["title"]) == ("Article 20", "Article 15")
