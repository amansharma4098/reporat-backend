# ============================================
# RepoRat Backend - GitHub Setup (Windows)
# ============================================
# Prerequisites:
#   1. Create empty repo on github.com/new -> reporat-backend
#   2. Replace YOUR_GITHUB_USERNAME below
#   3. Run this from INSIDE the reporat-backend folder
# ============================================

$GITHUB_USER = "amansharma4098"

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  RepoRat Backend - GitHub Setup" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Init and push
Write-Host "[1/5] Initializing git..." -ForegroundColor Yellow
git init

Write-Host "[2/5] Adding files..." -ForegroundColor Yellow
git add -A

Write-Host "[3/5] Committing..." -ForegroundColor Yellow
git commit -m "feat: initial commit - RepoRat backend

- FastAPI + Uvicorn async API server
- Claude AI test generation and failure analysis
- Static analysis via Ruff + Bandit
- Bug tracker connectors: Jira, Azure Boards, GitHub Issues, Linear
- Repo connectors: GitHub, Azure DevOps, GitLab
- WebSocket support for real-time scan updates
- Typer CLI with Rich output
- Docker support"

Write-Host "[4/5] Setting remote..." -ForegroundColor Yellow
git branch -M main
git remote add origin "https://github.com/$GITHUB_USER/reporat-backend.git"

Write-Host "[5/5] Pushing to GitHub..." -ForegroundColor Yellow
git push -u origin main

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Backend pushed successfully!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Repo: https://github.com/$GITHUB_USER/reporat-backend" -ForegroundColor White
Write-Host ""
Write-Host "  To run locally:" -ForegroundColor Yellow
Write-Host "    python -m venv venv"
Write-Host "    .\venv\Scripts\activate"
Write-Host "    pip install -r requirements.txt"
Write-Host "    copy .env.example .env"
Write-Host "    # Edit .env -> add ANTHROPIC_API_KEY"
Write-Host "    uvicorn main:app --reload --port 8000"
Write-Host ""
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan
