"""Retry decorators for API calls."""

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Retry decorator for external API calls (Anthropic, Tavily, GitHub)
# Retries up to 3 times with exponential backoff (2s, 4s, 8s)
api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    reraise=True,
)
