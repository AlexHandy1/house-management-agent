import re
from datetime import date, datetime

import requests
from bs4 import BeautifulSoup

from models.article import Article

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; house-management-agent)"}
REQUEST_TIMEOUT = 10

NRLA_NEWS_URL = "https://www.nrla.org.uk/news"
TDS_SITEMAP_URLS = [
    "https://www.tenancydepositscheme.com/sitemap-webarticle-1.xml",
    "https://www.tenancydepositscheme.com/sitemap-webarticle-weekly.xml",
]
TDS_SITEMAP_ENTRY_RE = re.compile(r"<url><loc>(.*?)</loc><lastmod>(.*?)</lastmod></url>")


def fetch_nrla_articles(cutoff: date) -> list[Article]:
    """NRLA's /news page is server-rendered HTML — pulled directly."""
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
        href = str(link.get("href", "") or "")
        title = heading.get_text(strip=True) if heading else str(link.get("title", "") or "")
        articles.append(
            Article(
                source="NRLA",
                title=title,
                url=f"https://www.nrla.org.uk{href}" if href.startswith("/") else href,
                published_date=published,
                summary=description.get_text(strip=True) if description else None,
            )
        )
    return articles


def _parse_nrla_date(text: str) -> date | None:
    try:
        day, month, year = (int(part) for part in text.split("/"))
        return date(year, month, day)
    except ValueError:
        return None


def fetch_tds_articles(cutoff: date) -> list[Article]:
    """TDS's /news page is a client-rendered Salesforce SPA with nothing
    server-side to pull from — pulled from its public sitemap XML instead
    (URL + lastmod), which carries no article body, so entries get a title
    derived from the URL slug and no summary."""
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
