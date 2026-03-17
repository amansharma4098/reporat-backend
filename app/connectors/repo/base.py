from abc import ABC, abstractmethod
from pathlib import Path


class RepoConnector(ABC):
    @abstractmethod
    async def clone(self, repo_url: str, branch: str, dest: Path) -> Path: ...

    @abstractmethod
    async def validate_url(self, repo_url: str) -> bool: ...

    @abstractmethod
    def get_auth_url(self, repo_url: str) -> str: ...
