import asyncio
from pathlib import Path
from git import Repo
from app.connectors.repo.base import RepoConnector
from app.core.config import settings


class AzureDevOpsConnector(RepoConnector):
    async def clone(self, repo_url: str, branch: str, dest: Path) -> Path:
        auth_url = self.get_auth_url(repo_url)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: Repo.clone_from(auth_url, str(dest), branch=branch, depth=1)
        )
        return dest

    async def validate_url(self, repo_url: str) -> bool:
        return "dev.azure.com" in repo_url or "visualstudio.com" in repo_url

    def get_auth_url(self, repo_url: str) -> str:
        pat = settings.azure_devops_pat
        if pat and "https://" in repo_url:
            return repo_url.replace("https://", f"https://pat:{pat}@")
        return repo_url
