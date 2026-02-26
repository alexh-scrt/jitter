"""Wrapper around the Tavily SDK for web search."""

from __future__ import annotations

from tavily import TavilyClient

from jitter.utils.logging import get_logger
from jitter.utils.retry import api_retry

logger = get_logger("tavily_client")


class TavilyService:
    """Thin wrapper around the Tavily search API with retry logic."""

    def __init__(self, api_key: str):
        self.client = TavilyClient(api_key=api_key)

    @api_retry
    def search(
        self,
        query: str,
        topic: str = "news",
        max_results: int = 5,
        time_range: str = "week",
    ) -> dict:
        """Search the web for trending content.

        Returns raw Tavily response with 'results' list containing
        title, url, content, and source for each result.
        """
        logger.debug("Searching: %r (topic=%s, max=%d)", query, topic, max_results)

        response = self.client.search(
            query=query,
            topic=topic,
            max_results=max_results,
            time_range=time_range,
        )

        result_count = len(response.get("results", []))
        logger.debug("Got %d results for query: %r", result_count, query)

        return response
