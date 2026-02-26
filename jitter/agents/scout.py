"""Scout agent: searches the internet for trending tech ideas using Tavily."""

from __future__ import annotations

import json
from datetime import date

from jitter.config import JitterConfig
from jitter.models import ScoutResult
from jitter.services.anthropic_client import AnthropicService
from jitter.services.tavily_client import TavilyService
from jitter.utils.logging import get_logger

logger = get_logger("scout")

SYSTEM_PROMPT = """You are a tech trend analyst. Given raw search results about trending
technology topics, extract distinct SOFTWARE PROJECT IDEAS that a developer could build
in a single day.

Rules:
- Each idea must be a concrete, buildable software project (CLI tool, API, library, web app, or script)
- Focus on ideas that are practical and useful, not just hype
- Score each idea's buzz/trendiness from 1 (low) to 10 (high) based on the search data
- Deduplicate similar ideas - merge them into one with the best description
- Exclude ideas that are just "use X framework" without a concrete product
- Aim for 5-10 distinct ideas
- Categorize each as: ai, web, devtools, data, security, automation, or other"""


class ScoutAgent:
    """Discovers trending ideas by searching the web and extracting project ideas."""

    def __init__(self, config: JitterConfig):
        self.config = config
        self.tavily = TavilyService(config.tavily_api_key)
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def search(self, past_idea_titles: list[str] | None = None) -> ScoutResult:
        """Search for trending ideas and return structured results."""
        # Select a subset of queries to use today (rotate by day)
        queries = self._select_queries()
        logger.info("Searching with %d queries...", len(queries))

        # Run searches and collect raw results
        raw_results = []
        for query in queries:
            try:
                response = self.tavily.search(
                    query=query,
                    topic=self.config.scout_topic,
                    max_results=self.config.scout_max_results_per_query,
                    time_range=self.config.scout_time_range,
                )
                for r in response.get("results", []):
                    raw_results.append(
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", ""),
                        }
                    )
            except Exception as e:
                logger.warning("Search failed for query %r: %s", query, e)

        if not raw_results:
            raise RuntimeError("All Tavily searches failed, no results to analyze")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in raw_results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                unique_results.append(r)

        logger.info("Got %d unique results from %d total", len(unique_results), len(raw_results))

        # Ask Claude to extract and score project ideas
        exclusion_note = ""
        if past_idea_titles:
            exclusion_note = (
                f"\n\nDo NOT include ideas similar to these previously built projects: "
                f"{json.dumps(past_idea_titles)}"
            )

        user_message = (
            f"Extract buildable software project ideas from these search results:\n\n"
            f"{json.dumps(unique_results, indent=2)}"
            f"{exclusion_note}"
        )

        result = self.anthropic.generate_structured(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            output_model=ScoutResult,
        )

        # Attach the queries used
        result.search_queries_used = queries
        logger.info("Extracted %d project ideas", len(result.ideas))
        return result

    def _select_queries(self) -> list[str]:
        """Rotate through queries so different ones are used each day."""
        all_queries = self.config.scout_search_queries
        if len(all_queries) <= 4:
            return all_queries

        # Use day of year to rotate which queries to use
        day = date.today().timetuple().tm_yday
        n = min(4, len(all_queries))
        start = day % len(all_queries)

        selected = []
        for i in range(n):
            idx = (start + i) % len(all_queries)
            selected.append(all_queries[idx])

        return selected
