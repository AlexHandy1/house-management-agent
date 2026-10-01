"""PROTOTYPE — throwaway (see README.md). Thin HTTP wrapper around
news_feed_scrape_prototype.fetch_recent_articles(), so the real app/frontend's
dev server can fetch it directly for a visual check. Deliberately kept out of
app/backend entirely — a separate process on its own port, not a route on the
production API.

Run: uvicorn news_feed_api_prototype:app --port 8001 --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from news_feed_scrape_prototype import Article, fetch_recent_articles

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prototype only, served from a local static HTML file
    allow_methods=["GET"],
)


@app.get("/news-feed")
def news_feed() -> list[Article]:
    return fetch_recent_articles()
