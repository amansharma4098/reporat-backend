import shutil
from pathlib import Path
from app.core.config import settings
from app.core.models import RepoSource
from app.connectors.repo.github import GitHubConnector
from app.connectors.repo.azure_devops import AzureDevOpsConnector
from app.connectors.repo.gitlab import GitLabConnector

CONNECTOR_MAP = {
    RepoSource.GITHUB: GitHubConnector,
    RepoSource.AZURE_DEVOPS: AzureDevOpsConnector,
    RepoSource.GITLAB: GitLabConnector,
}


async def clone_repo(repo_url: str, branch: str, repo_source: RepoSource, scan_id: str) -> Path:
    dest = Path(settings.scan_temp_dir) / scan_id
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    connector_cls = CONNECTOR_MAP.get(repo_source)
    if not connector_cls:
        raise ValueError(f"Unsupported repo source: {repo_source}")

    connector = connector_cls()
    if not await connector.validate_url(repo_url):
        raise ValueError(f"Invalid URL for {repo_source.value}: {repo_url}")

    await connector.clone(repo_url, branch, dest)

    # Verify clone produced files
    if not dest.exists() or not dest.is_dir():
        raise RuntimeError(f"Clone failed: destination {dest} does not exist after clone")
    contents = list(dest.iterdir())
    if not contents:
        raise RuntimeError(f"Clone failed: destination {dest} is empty after clone")

    return dest


def cleanup_repo(scan_id: str):
    dest = Path(settings.scan_temp_dir) / scan_id
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
