from typing import Any

from fastapi import APIRouter

from services.articles_table import list_recent_articles

router = APIRouter()


@router.get("/api/news-feed")
def get_news_feed() -> list[dict[str, Any]]:
    return list_recent_articles()
