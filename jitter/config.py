"""Configuration loading from YAML + environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings
from ruamel.yaml import YAML


class JitterConfig(BaseSettings):
    """Jitter configuration. Env vars override YAML values."""

    # API keys (from environment only)
    anthropic_api_key: str = Field(alias="ANTHROPIC_API_KEY", default="")
    tavily_api_key: str = Field(alias="TAVILY_API_KEY", default="")
    github_token: str = Field(alias="GITHUB_TOKEN", default="")

    # Output
    output_dir: Path = Path("./output")

    # GitHub
    github_org: str | None = None
    github_private: bool = False
    github_topic_tags: list[str] = ["ai-generated", "jitter"]

    # Models
    model_default: str = "claude-sonnet-4-6"
    model_quality: str = "claude-opus-4-6"
    model_max_tokens: int = 32768

    # Scout
    scout_search_queries: list[str] = [
        "trending developer tools 2026",
        "new open source projects this week",
        "trending GitHub repositories this week",
    ]
    scout_max_results_per_query: int = 5
    scout_topic: str = "news"
    scout_time_range: str = "week"

    # Pipeline
    pipeline_max_phases: int = 6
    pipeline_max_files_per_phase: int = 5
    pipeline_test_timeout_seconds: int = 60
    pipeline_max_retries_per_phase: int = 2

    # Logging
    logging_level: str = "INFO"
    logging_file: str = "./jitter.log"

    # History
    history_db_path: str = "./jitter_history.db"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


def load_config(config_path: str = "config.yaml") -> JitterConfig:
    """Load configuration from YAML file, with env var overrides."""
    yaml = YAML()
    yaml_data: dict = {}

    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            yaml_data = yaml.load(f) or {}

    # Flatten nested YAML into flat keys matching JitterConfig fields
    flat = {}
    if "output_dir" in yaml_data:
        flat["output_dir"] = yaml_data["output_dir"]

    github = yaml_data.get("github", {})
    if github:
        if "org" in github:
            flat["github_org"] = github["org"]
        if "private" in github:
            flat["github_private"] = github["private"]
        if "topic_tags" in github:
            flat["github_topic_tags"] = github["topic_tags"]

    models = yaml_data.get("models", {})
    if models:
        if "default" in models:
            flat["model_default"] = models["default"]
        if "quality" in models:
            flat["model_quality"] = models["quality"]
        if "max_tokens" in models:
            flat["model_max_tokens"] = models["max_tokens"]

    scout = yaml_data.get("scout", {})
    if scout:
        if "search_queries" in scout:
            flat["scout_search_queries"] = scout["search_queries"]
        if "max_results_per_query" in scout:
            flat["scout_max_results_per_query"] = scout["max_results_per_query"]
        if "topic" in scout:
            flat["scout_topic"] = scout["topic"]
        if "time_range" in scout:
            flat["scout_time_range"] = scout["time_range"]

    pipeline = yaml_data.get("pipeline", {})
    if pipeline:
        if "max_phases" in pipeline:
            flat["pipeline_max_phases"] = pipeline["max_phases"]
        if "max_files_per_phase" in pipeline:
            flat["pipeline_max_files_per_phase"] = pipeline["max_files_per_phase"]
        if "test_timeout_seconds" in pipeline:
            flat["pipeline_test_timeout_seconds"] = pipeline["test_timeout_seconds"]
        if "max_retries_per_phase" in pipeline:
            flat["pipeline_max_retries_per_phase"] = pipeline["max_retries_per_phase"]

    logging_cfg = yaml_data.get("logging", {})
    if logging_cfg:
        if "level" in logging_cfg:
            flat["logging_level"] = logging_cfg["level"]
        if "file" in logging_cfg:
            flat["logging_file"] = logging_cfg["file"]

    history = yaml_data.get("history", {})
    if history:
        if "db_path" in history:
            flat["history_db_path"] = history["db_path"]

    return JitterConfig(**flat)
