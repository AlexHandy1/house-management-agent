import argparse
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from dotenv import load_dotenv

from models.article import Article
from services import articles_table, news_data_pull

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 2


def run(lookback_days: int) -> bool:
    """Commits per source: one source failing doesn't lose the other's data
    this run. Returns False if any source failed, True only if every source
    succeeded."""
    cutoff = datetime.now(UTC).date() - timedelta(days=lookback_days)
    nrla_succeeded = _pull_source("NRLA", news_data_pull.fetch_nrla_articles, cutoff)
    tds_succeeded = _pull_source(
        "Tenancy Deposit Scheme", news_data_pull.fetch_tds_articles, cutoff
    )
    return nrla_succeeded and tds_succeeded


def _pull_source(source_name: str, fetch: Callable[[date], list[Article]], cutoff: date) -> bool:
    try:
        articles = fetch(cutoff)
        inserted = articles_table.save_articles(articles)
        logger.info(
            "News feed pull succeeded",
            extra={"source": source_name, "fetched": len(articles), "inserted": inserted},
        )
        return True
    except Exception:
        logger.exception("News feed pull failed", extra={"source": source_name})
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull NRLA/TDS news articles into the DB.")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if not run(args.lookback_days):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
