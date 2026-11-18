from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    AsyncWebCrawler = None


class WebResearch:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(settings.crawl_timeout_seconds, connect=8.0)

    async def _public_http_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                return False
            addresses = await asyncio.to_thread(
                socket.getaddrinfo, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), 0, socket.SOCK_STREAM
            )
            return all(not ipaddress.ip_address(item[4][0]).is_private and not ipaddress.ip_address(item[4][0]).is_loopback and not ipaddress.ip_address(item[4][0]).is_link_local for item in addresses)
        except (OSError, ValueError, UnicodeError):
            return False

    async def _search_results(self, query: str, limit: int) -> list[dict[str, str]]:
        endpoint = settings.searxng_url.rstrip("/") + "/search"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.get(endpoint, params={"q": query, "format": "json", "language": "all"})
                response.raise_for_status()
                payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            selected: list[dict[str, str]] = []
            for item in results:
                url = str(item.get("url", ""))
                if url and await self._public_http_url(url):
                    selected.append({
                        "title": str(item.get("title", ""))[:300],
                        "url": url,
                        "snippet": str(item.get("content", ""))[:1000],
                    })
                if len(selected) >= max(1, min(limit, 5)):
                    break
            return selected
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("SearXNG request failed: %s", exc)
            return []
        except Exception as exc:
            logger.warning("Unexpected search error: %s", exc)
            return []

    async def _crawl_one(self, url: str) -> str:
        if AsyncWebCrawler is None:
            return ""
        try:
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await asyncio.wait_for(
                    crawler.arun(url=url, timeout=settings.crawl_timeout_seconds),
                    timeout=settings.crawl_timeout_seconds,
                )
            if getattr(result, "success", True) is False:
                return ""
            markdown = getattr(result, "markdown", "")
            if not isinstance(markdown, str):
                markdown = getattr(markdown, "raw_markdown", "")
            return markdown.strip()[:16000] if isinstance(markdown, str) else ""
        except asyncio.TimeoutError:
            logger.warning("Crawl timed out for %s", url)
            return ""
        except Exception as exc:
            logger.warning("Crawl failed for %s: %s", url, exc)
            return ""

    async def search(self, query: str, limit: int = 3) -> dict[str, object]:
        query = query.strip()
        if not query:
            return {"query": query, "results": []}
        results = await self._search_results(query, limit)
        pages = await asyncio.gather(*(self._crawl_one(item["url"]) for item in results), return_exceptions=True)
        output = []
        for item, page in zip(results, pages):
            text = page if isinstance(page, str) else ""
            output.append({**item, "markdown": text or item["snippet"]})
        return {"query": query, "results": output}


web_research = WebResearch()
