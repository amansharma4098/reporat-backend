#!/bin/bash
# ============================================
# RepoRat Backend - GitHub Setup (Linux/Mac)
# ============================================
# Prerequisites:
#   1. Create empty repo on github.com/new -> reporat-backend
#   2. Replace YOUR_GITHUB_USERNAME below
#   3. Run this from INSIDE the reporat-backend folder
# ============================================

GITHUB_USER="amansharma4098"

set -e

echo ""
echo "========================================="
echo "  RepoRat Backend - GitHub Setup"
echo "========================================="
echo ""

echo "[1/5] Initializing git..."
git init

echo "[2/5] Adding files..."
git add -A

echo "[3/5] Committing..."
git commit -m "feat: initial commit - RepoRat backend

- FastAPI + Uvicorn async API server
- Claude AI test generation and failure analysis
- Static analysis via Ruff + Bandit
- Bug tracker connectors: Jira, Azure Boards, GitHub Issues, Linear
- Repo connectors: GitHub, Azure DevOps, GitLab
- WebSocket support for real-time scan updates
- Typer CLI with Rich output
- Docker support"

echo "[4/5] Setting remote..."
git branch -M main
git remote add origin "https://github.com/${GITHUB_USER}/reporat-backend.git"

echo "[5/5] Pushing to GitHub..."
git push -u origin main

echo ""
echo "========================================="
echo "  Backend pushed successfully!"
echo "========================================="
echo ""
echo "  Repo: https://github.com/${GITHUB_USER}/reporat-backend"
echo ""
echo "  To run locally:"
echo "    python -m venv venv"
echo "    source venv/bin/activate"
echo "    pip install -r requirements.txt"
echo "    cp .env.example .env"
echo "    # Edit .env -> add ANTHROPIC_API_KEY"
echo "    uvicorn main:app --reload --port 8000"
echo ""
echo "  API docs: http://localhost:8000/docs"
echo "========================================="
