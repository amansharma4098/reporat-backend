# RepoRat Backend

AI-powered repository scanner — auto-generates tests, runs static analysis, and files bugs to Jira, Azure DevOps, GitHub Issues, or Linear.

## Stack

- **FastAPI** + **Uvicorn** — async API server
- **Anthropic Claude** — AI test generation & failure analysis
- **Ruff + Bandit** — static analysis
- **GitPython** — repo cloning
- **httpx** — async HTTP for bug tracker APIs
- **Typer + Rich** — CLI interface

## Quick Start

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn main:app --reload --port 8000
```

## CLI Usage

```bash
python cli.py scan https://github.com/user/repo --tracker jira
python cli.py test-connector jira
python cli.py scan https://github.com/user/repo --no-file  # dry run
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scan` | Trigger a full scan |
| GET | `/api/scan/{id}` | Get scan status/results |
| GET | `/api/scan/{id}/summary` | Get scan summary |
| GET | `/api/connectors` | List configured connectors |
| POST | `/api/connectors/{type}/test` | Test connector connection |
| GET | `/health` | Health check |

## Architecture

```
Repo URL → Clone → Static Analysis (Ruff/Bandit)
                 → AI Test Generation (Claude)
                 → Run Tests → Analyze Failures (Claude)
                 → File Bugs → [Jira | Azure | GitHub | Linear]
```
