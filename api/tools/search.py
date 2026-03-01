"""BrainC v0.4 — Web search via a local SearXNG instance."""

import re

import httpx
from bs4 import BeautifulSoup

SEARXNG_URL = "http://localhost:8080"
_SETUP_MSG = (
    "SearXNG is not running. Start it with:\n"
    "  cd tools/searxng && docker compose up -d\n"
    "Then wait ~10 seconds for the container to be ready."
)


async def search(query: str, num_results: int = 5) -> list[dict]:
    """Query the local SearXNG instance and return structured results.

    Returns a list of {title, url, snippet} dicts. Falls back gracefully
    if SearXNG is not available.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={"q": query, "format": "json", "categories": "general"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        return [{"title": "SearXNG unavailable", "url": "", "snippet": _SETUP_MSG}]
    except Exception as exc:
        return [{"title": "Search error", "url": "", "snippet": str(exc)}]

    results = []
    for item in data.get("results", [])[:num_results]:
        results.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": _clean(item.get("content", "")),
            }
        )
    return results


def _clean(html: str) -> str:
    """Strip HTML tags, collapse whitespace, and truncate to 300 chars."""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300] + ("…" if len(text) > 300 else "")
