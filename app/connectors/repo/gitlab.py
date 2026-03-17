import asyncio
from pathlib import Path
from git import Repo
from app.connectors.repo.base import RepoConnector
from app.core.config import settings


class GitLabConnector(RepoConnector):
    async def clone(self, repo_url: str, branch: str, dest: Path) -> Path:
        auth_url = self.get_auth_url(repo_url)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: Repo.clone_from(auth_url, str(dest), branch=branch, depth=1)
        )
        return dest

    async def validate_url(self, repo_url: str) -> bool:
        return "gitlab.com" in repo_url or "gitlab" in repo_url.lower()

    def get_auth_url(self, repo_url: str) -> str:
        token = settings.gitlab_token
        if token and "https://" in repo_url:
            return repo_url.replace("https://", f"https://oauth2:{token}@")
        return repo_url
