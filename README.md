# Jitter

An autonomous AI agent that discovers trending tech ideas, designs projects around them, and ships working code to GitHub daily.

## How It Works

Jitter runs a daily 8-step pipeline:

```
Scout → Evaluate → Architect → Plan → Code → Test → Document → Publish
```

1. **Scout** - Searches the web for trending tech ideas using Tavily
2. **Evaluate** - Claude scores each idea on feasibility, novelty, and usefulness
3. **Architect** - Claude designs a complete project blueprint (files, tech stack, features)
4. **Plan** - Claude breaks the blueprint into 3-6 implementation phases
5. **Code** - Claude generates complete code for each phase, with full context from prior phases
6. **Test** - Runs pytest on the generated code in an isolated environment
7. **Document** - Claude generates a comprehensive README.md
8. **Publish** - Creates a GitHub repo and pushes each phase as a separate commit

Each project gets a clean git history with small, meaningful commits.

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd jitter
pip install -e ".[dev]"

# Configure API keys
cp .env.example .env
# Edit .env with your keys:
#   ANTHROPIC_API_KEY=sk-ant-...
#   TAVILY_API_KEY=tvly-...
#   GITHUB_TOKEN=ghp_...

# Run the pipeline
python -m jitter run

# Dry run (no GitHub push, saves locally)
python -m jitter run --dry-run

# Check status
python -m jitter status
python -m jitter history
```

## Configuration

Edit `config.yaml` to customize:

```yaml
output_dir: "./output"          # Local save directory

github:
  org: null                     # GitHub org (null = personal account)
  private: false                # Public/private repos
  topic_tags: ["ai-generated"]  # Repo topics

models:
  default: "claude-sonnet-4-6"  # Model for all generation
  quality: "claude-opus-4-6"    # Fallback for quality issues
  max_tokens: 8000

scout:
  search_queries:               # Tavily search queries (rotated daily)
    - "trending developer tools 2026"
    - "new open source projects this week"
  max_results_per_query: 5
  topic: "news"
  time_range: "week"

pipeline:
  max_phases: 6                 # Max implementation phases
  max_files_per_phase: 5        # Max files per phase
  test_timeout_seconds: 60      # Test execution timeout
```

API keys are set via environment variables or `.env` file.

## Project Structure

```
jitter/
├── jitter/
│   ├── cli.py                 # Click CLI (run, status, history)
│   ├── config.py              # YAML + env var configuration
│   ├── models.py              # Pydantic data models
│   ├── pipeline.py            # Main orchestrator
│   ├── agents/
│   │   ├── scout.py           # Tavily trend search
│   │   ├── evaluator.py       # Idea scoring & selection
│   │   ├── architect.py       # Project blueprint design
│   │   ├── planner.py         # Phase breakdown
│   │   ├── coder.py           # Code generation per phase
│   │   └── documenter.py      # README generation
│   ├── services/
│   │   ├── anthropic_client.py  # Claude API wrapper
│   │   ├── tavily_client.py     # Tavily search wrapper
│   │   ├── github_service.py    # PyGithub Git Data API
│   │   └── test_runner.py       # Subprocess pytest runner
│   ├── store/
│   │   └── history.py          # SQLite history tracking
│   └── utils/
│       ├── logging.py          # Rich logging
│       └── retry.py            # Tenacity retry decorator
├── tests/                      # pytest test suite
├── config.yaml                 # Default configuration
├── pyproject.toml
└── .env.example
```

## Architecture Highlights

- **Structured outputs** - Every Claude call uses `messages.parse()` with Pydantic models, guaranteeing schema-conforming responses
- **Context accumulation** - The coder agent includes all previously generated files in each phase prompt, so Claude sees the full project state
- **Atomic commits** - Uses PyGithub's Git Data API (tree/commit/ref) to push multi-file commits without local git
- **Deduplication** - SQLite history tracks past projects to avoid rebuilding similar ideas
- **Retry logic** - All API calls use exponential backoff via tenacity

## Requirements

- Python 3.12+
- [Anthropic API key](https://console.anthropic.com/)
- [Tavily API key](https://tavily.com/)
- [GitHub personal access token](https://github.com/settings/tokens) (with `repo` scope)

## Running Tests

```bash
python -m pytest tests/ -v
```

## License

MIT
