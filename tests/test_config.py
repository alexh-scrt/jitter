"""Tests for configuration loading."""

import os

import pytest

from jitter.config import JitterConfig, load_config


def test_load_config_from_yaml():
    """Should load config from the project's config.yaml."""
    cfg = load_config("config.yaml")
    assert cfg.model_default == "claude-sonnet-4-6"
    assert cfg.pipeline_max_phases == 6
    assert cfg.scout_topic == "news"
    assert len(cfg.scout_search_queries) > 0


def test_load_config_defaults_when_no_file():
    """Should use defaults when config file doesn't exist."""
    cfg = load_config("/nonexistent/config.yaml")
    assert cfg.model_default == "claude-sonnet-4-6"
    assert cfg.pipeline_max_phases == 6


def test_config_env_override(monkeypatch):
    """Environment variables should override YAML values."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-123")
    cfg = load_config("config.yaml")
    assert cfg.anthropic_api_key == "test-key-123"


def test_config_has_expected_fields():
    """Config should have all expected fields with defaults."""
    cfg = JitterConfig()
    assert hasattr(cfg, "output_dir")
    assert hasattr(cfg, "github_org")
    assert hasattr(cfg, "model_default")
    assert hasattr(cfg, "scout_search_queries")
    assert hasattr(cfg, "pipeline_max_phases")
    assert hasattr(cfg, "history_db_path")
