"""Tests for the coder agent, including truncation fallback."""

from unittest.mock import MagicMock, patch, call

import pytest

from jitter.agents.coder import CoderAgent
from jitter.models import (
    FileSpec,
    GeneratedFile,
    ImplementationPhase,
    PhaseCodeResult,
    PlannerResult,
    ProjectBlueprint,
    ProjectType,
)
from jitter.services.anthropic_client import OutputTruncatedError


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.anthropic_api_key = "fake-key"
    cfg.model_default = "claude-sonnet-4-6"
    cfg.model_max_tokens = 16384
    return cfg


@pytest.fixture
def blueprint():
    return ProjectBlueprint(
        project_name="test_proj",
        project_type=ProjectType.CLI_TOOL,
        description="A test project",
        tech_stack=["Python"],
        file_structure=[
            FileSpec(path="main.py", purpose="Entry point"),
            FileSpec(path="utils.py", purpose="Utilities"),
        ],
        dependencies=["click"],
        key_features=["Feature 1"],
    )


@pytest.fixture
def plan():
    return PlannerResult(
        phases=[
            ImplementationPhase(
                phase_number=1,
                title="Setup",
                description="Project scaffold",
                files_to_create=["main.py", "utils.py"],
                commit_message="feat: init",
            ),
        ],
        estimated_total_files=2,
        testing_strategy="pytest",
    )


@pytest.fixture
def batch_result():
    return PhaseCodeResult(
        phase_number=1,
        files=[
            GeneratedFile(path="main.py", content="# main", language="python"),
            GeneratedFile(path="utils.py", content="# utils", language="python"),
        ],
    )


@patch("jitter.agents.coder.AnthropicService")
def test_batch_generation_succeeds(mock_cls, mock_config, blueprint, plan, batch_result):
    """Normal case: batch generation works, no fallback needed."""
    mock_svc = MagicMock()
    mock_svc.generate_structured.return_value = batch_result
    mock_cls.return_value = mock_svc

    coder = CoderAgent(mock_config)
    result = coder.generate(blueprint, plan, plan.phases[0], [])

    assert isinstance(result, PhaseCodeResult)
    assert len(result.files) == 2
    # Only one API call (batch)
    assert mock_svc.generate_structured.call_count == 1


@patch("jitter.agents.coder.AnthropicService")
def test_fallback_to_per_file_on_truncation(mock_cls, mock_config, blueprint, plan):
    """When batch is truncated, should fall back to per-file generation."""
    mock_svc = MagicMock()

    # First call (batch) raises truncation error
    # Subsequent calls (per-file) return individual files
    mock_svc.generate_structured.side_effect = [
        OutputTruncatedError(output_tokens=16384, max_tokens=16384),
        GeneratedFile(path="main.py", content="# main code", language="python"),
        GeneratedFile(path="utils.py", content="# utils code", language="python"),
    ]
    mock_cls.return_value = mock_svc

    coder = CoderAgent(mock_config)
    result = coder.generate(blueprint, plan, plan.phases[0], [])

    assert isinstance(result, PhaseCodeResult)
    assert len(result.files) == 2
    assert result.files[0].path == "main.py"
    assert result.files[1].path == "utils.py"
    # 1 batch attempt + 2 per-file calls = 3 total
    assert mock_svc.generate_structured.call_count == 3


@patch("jitter.agents.coder.AnthropicService")
def test_per_file_sorts_test_files(mock_cls, mock_config, blueprint):
    """Per-file fallback should sort test files into test_files list."""
    plan = PlannerResult(
        phases=[
            ImplementationPhase(
                phase_number=1,
                title="Setup",
                description="Files and tests",
                files_to_create=["main.py", "tests/test_main.py"],
                commit_message="feat: init",
            ),
        ],
        estimated_total_files=2,
        testing_strategy="pytest",
    )

    mock_svc = MagicMock()
    mock_svc.generate_structured.side_effect = [
        OutputTruncatedError(output_tokens=16384, max_tokens=16384),
        GeneratedFile(path="main.py", content="# main", language="python"),
        GeneratedFile(path="tests/test_main.py", content="# test", language="python"),
    ]
    mock_cls.return_value = mock_svc

    coder = CoderAgent(mock_config)
    result = coder.generate(blueprint, plan, plan.phases[0], [])

    assert len(result.files) == 1
    assert result.files[0].path == "main.py"
    assert len(result.test_files) == 1
    assert result.test_files[0].path == "tests/test_main.py"


@patch("jitter.agents.coder.AnthropicService")
def test_accumulated_files_passed_as_context(mock_cls, mock_config, blueprint, plan, batch_result):
    """Previous phase files should be included in the prompt."""
    mock_svc = MagicMock()
    mock_svc.generate_structured.return_value = batch_result
    mock_cls.return_value = mock_svc

    prior_files = [
        GeneratedFile(path="setup.py", content="# setup", language="python"),
    ]

    coder = CoderAgent(mock_config)
    coder.generate(blueprint, plan, plan.phases[0], prior_files)

    call_args = mock_svc.generate_structured.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "setup.py" in user_msg
    assert "# setup" in user_msg


def test_output_truncated_error():
    """OutputTruncatedError should contain useful info."""
    err = OutputTruncatedError(output_tokens=8000, max_tokens=8000)
    assert "8000" in str(err)
    assert err.output_tokens == 8000
    assert err.max_tokens == 8000
