"""PROTOTYPE — throwaway (see README.md). Answers: what does a pulled news feed
look like for real, from the two sources named in the PRD (../docs/prds/
production-v1-prd-200926.md, Story 3/4)?

Deterministic scraping, no LLM involved — the listing pages are structured enough
not to need one:
- NRLA's /news page is server-rendered HTML — scraped directly with BeautifulSoup.
- TDS's /news page is a client-rendered Salesforce SPA (confirmed by curling it:
  the HTML is just a <webruntime-app> shell, even for individual article pages) —
  scraped via its public sitemap instead (URL + lastmod), which is itself
  server-rendered XML. No article body available this way, so TDS entries carry a
  derived title (from the URL slug) and no summary.

No persistence — re-fetches live on every call. LOOKBACK_DAYS=7 because neither
source has published anything in the PRD's target 2-day window right now; 7 was
chosen just to have something to look at (see ../docs/status_docs/
WORK_SUMMARY_300926.md discussion).

Run: python news_feed_scrape_prototype.py
"""

import re
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel

LOOKBACK_DAYS = 7
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; house-management-agent-prototype)"}
REQUEST_TIMEOUT = 10

NRLA_NEWS_URL = "https://www.nrla.org.uk/news"
TDS_SITEMAP_URLS = [
    "https://www.tenancydepositscheme.com/sitemap-webarticle-1.xml",
    "https://www.tenancydepositscheme.com/sitemap-webarticle-weekly.xml",
]
TDS_SITEMAP_ENTRY_RE = re.compile(r"<url><loc>(.*?)</loc><lastmod>(.*?)</lastmod></url>")


class Article(BaseModel):
    """In-memory only — the entity Story 4 of the PRD eventually persists, not
    built here on purpose: this prototype is checking what it looks like, not
    whether it's durable."""

    source: str
    title: str
    url: str
    published_date: date | None
    summary: str | None


def fetch_recent_articles() -> list[Article]:
    cutoff = date.today() - timedelta(days=LOOKBACK_DAYS)
    articles = _fetch_nrla(cutoff) + _fetch_tds(cutoff)
    return sorted(articles, key=lambda a: a.published_date or date.min, reverse=True)


def _fetch_nrla(cutoff: date) -> list[Article]:
    response = requests.get(NRLA_NEWS_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    articles = []
    for link in soup.select("a.news-article"):
        date_text = link.select_one(".news-article-meta-date")
        published = _parse_nrla_date(date_text.get_text(strip=True)) if date_text else None
        if published is None or published < cutoff:
            continue
        heading = link.select_one("h3")
        description = link.select_one(".news-article-description")
        href = link.get("href", "")
        articles.append(
            Article(
                source="NRLA",
                title=heading.get_text(strip=True) if heading else link.get("title", ""),
                url=f"https://www.nrla.org.uk{href}" if href.startswith("/") else href,
                published_date=published,
                summary=description.get_text(strip=True) if description else None,
            )
        )
    return articles


def _parse_nrla_date(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _fetch_tds(cutoff: date) -> list[Article]:
    seen_urls: dict[str, date] = {}
    for sitemap_url in TDS_SITEMAP_URLS:
        response = requests.get(sitemap_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        for url, lastmod in TDS_SITEMAP_ENTRY_RE.findall(response.text):
            published = datetime.fromisoformat(lastmod.replace("Z", "+00:00")).date()
            if published >= cutoff:
                seen_urls[url] = max(published, seen_urls.get(url, date.min))

    return [
        Article(
            source="Tenancy Deposit Scheme",
            title=_title_from_slug(url),
            url=url,
            published_date=published,
            summary=None,
        )
        for url, published in seen_urls.items()
    ]


def _title_from_slug(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ")


if __name__ == "__main__":
    for article in fetch_recent_articles():
        print(f"[{article.source}] {article.title} ({article.published_date})")
        print(f"  {article.url}")
        if article.summary:
            print(f"  {article.summary}")
        print()
