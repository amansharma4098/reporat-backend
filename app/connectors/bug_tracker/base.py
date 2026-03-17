from abc import ABC, abstractmethod
from app.core.models import Issue


class BugTrackerConnector(ABC):
    @abstractmethod
    async def file_bug(self, issue: Issue) -> dict: ...

    @abstractmethod
    async def file_bugs(self, issues: list[Issue]) -> list[dict]: ...

    @abstractmethod
    async def test_connection(self) -> bool: ...
