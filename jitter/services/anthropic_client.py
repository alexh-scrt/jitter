"""Wrapper around the Anthropic SDK for structured output generation.

Uses streaming for all API calls to avoid the Anthropic SDK's 10-minute
timeout restriction on non-streaming requests with high max_tokens.
"""

from __future__ import annotations

import json
import re
from typing import TypeVar

from anthropic import Anthropic
from pydantic import BaseModel

from jitter.utils.logging import get_logger
from jitter.utils.retry import api_retry

logger = get_logger("anthropic_client")

T = TypeVar("T", bound=BaseModel)


# Valid JSON escape characters after a backslash
_VALID_JSON_ESCAPES = frozenset('"\\bfnrtu/')


def _fix_invalid_json_escapes(text: str) -> str:
    """Replace invalid JSON escape sequences with double-backslash equivalents.

    Claude sometimes generates code containing regex patterns (e.g. \\d, \\s, \\w)
    inside JSON string values. These are not valid JSON escapes and cause parse
    errors. This function escapes them so the JSON is parseable.
    """

    def _replacer(match: re.Match) -> str:
        char = match.group(1)
        if char in _VALID_JSON_ESCAPES:
            return match.group(0)  # Leave valid escapes alone
        return "\\\\" + char  # Double the backslash for invalid escapes

    # Match any backslash followed by a single character
    return re.sub(r"\\(.)", _replacer, text)


class OutputTruncatedError(Exception):
    """Raised when Claude's response was truncated due to max_tokens limit."""

    def __init__(self, output_tokens: int, max_tokens: int):
        self.output_tokens = output_tokens
        self.max_tokens = max_tokens
        super().__init__(
            f"Response truncated: used {output_tokens}/{max_tokens} tokens. "
            f"Increase max_tokens or reduce prompt size."
        )


class AnthropicService:
    """Thin wrapper around the Anthropic Messages API with structured output.

    All calls use streaming internally to avoid the SDK's 10-minute
    non-streaming timeout limit for large max_tokens values.
    """

    def __init__(self, api_key: str, default_model: str = "claude-sonnet-4-6"):
        self.client = Anthropic(api_key=api_key)
        self.default_model = default_model

    @api_retry
    def generate_structured(
        self,
        system: str,
        user_message: str,
        output_model: type[T],
        model: str | None = None,
        max_tokens: int = 32768,
    ) -> T:
        """Generate a structured response matching the given Pydantic model.

        Uses streaming to collect the full response, then checks for
        truncation before parsing. Raises OutputTruncatedError if cut off.
        """
        used_model = model or self.default_model
        logger.debug(
            "Calling %s with output_model=%s (max_tokens=%d)",
            used_model,
            output_model.__name__,
            max_tokens,
        )

        # Build the system prompt that instructs Claude to output JSON
        schema_json = json.dumps(output_model.model_json_schema(), indent=2)
        structured_system = (
            f"{system}\n\n"
            f"You MUST respond with valid JSON matching this exact schema:\n"
            f"```json\n{schema_json}\n```\n\n"
            f"Respond ONLY with the JSON object. No markdown fences, no commentary."
        )

        # Use streaming to avoid the SDK's non-streaming timeout limit
        with self.client.messages.stream(
            model=used_model,
            max_tokens=max_tokens,
            system=structured_system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()

        logger.debug(
            "Tokens used: input=%d output=%d, stop_reason=%s",
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.stop_reason,
        )

        # Check for truncation BEFORE attempting to parse
        if response.stop_reason == "max_tokens":
            logger.warning(
                "Response truncated at %d tokens (limit: %d)",
                response.usage.output_tokens,
                max_tokens,
            )
            raise OutputTruncatedError(response.usage.output_tokens, max_tokens)

        raw_text = response.content[0].text

        # Strip markdown fences if Claude wrapped the JSON
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_text = "\n".join(lines)

        # Parse and validate with Pydantic
        try:
            parsed = output_model.model_validate_json(raw_text)
        except Exception:
            # Claude sometimes emits invalid JSON escape sequences (e.g. \d, \s
            # from regex patterns in generated code). Fix them and retry.
            raw_text = _fix_invalid_json_escapes(raw_text)
            parsed = output_model.model_validate_json(raw_text)
        return parsed

    @api_retry
    def generate_text(
        self,
        system: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int = 32768,
    ) -> str:
        """Generate a plain text response (streaming)."""
        used_model = model or self.default_model

        with self.client.messages.stream(
            model=used_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            response = stream.get_final_message()

        return response.content[0].text
