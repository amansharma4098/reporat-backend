import httpx
import base64
from app.connectors.bug_tracker.base import BugTrackerConnector
from app.core.models import Issue, Severity
from app.core.config import settings

SEVERITY_MAP = {
    Severity.CRITICAL: "1 - Critical",
    Severity.HIGH: "2 - High",
    Severity.MEDIUM: "3 - Medium",
    Severity.LOW: "4 - Low",
    Severity.INFO: "4 - Low",
}


class AzureBoardsConnector(BugTrackerConnector):
    def __init__(self, credentials: dict | None = None):
        if credentials:
            self.org = credentials["org"]
            self.project = credentials["project"]
            self.pat = credentials["pat"]
        else:
            self.org = settings.azure_boards_org
            self.project = settings.azure_boards_project
            self.pat = settings.azure_boards_pat
        self.base_url = f"https://dev.azure.com/{self.org}/{self.project}/_apis"

    def _headers(self) -> dict:
        encoded = base64.b64encode(f":{self.pat}".encode()).decode()
        return {
            "Content-Type": "application/json-patch+json",
            "Authorization": f"Basic {encoded}",
        }

    def _build_payload(self, issue: Issue) -> list[dict]:
        return [
            {"op": "add", "path": "/fields/System.Title", "value": issue.title},
            {"op": "add", "path": "/fields/System.Description", "value": issue.description},
            {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Severity", "value": SEVERITY_MAP.get(issue.severity, "3 - Medium")},
            {"op": "add", "path": "/fields/System.Tags", "value": f"reporat;{issue.source}"},
        ]

    async def file_bug(self, issue: Issue) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/wit/workitems/$Bug?api-version=7.1",
                json=self._build_payload(issue),
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "tracker": "azure_boards",
                "id": data["id"],
                "url": data["_links"]["html"]["href"],
                "issue_id": issue.id,
            }

    async def file_bugs(self, issues: list[Issue]) -> list[dict]:
        results = []
        for issue in issues:
            result = await self.file_bug(issue)
            results.append(result)
        return results

    async def test_connection(self) -> bool:
        try:
            encoded = base64.b64encode(f":{self.pat}".encode()).decode()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/wit/workitemtypes?api-version=7.1",
                    headers={"Authorization": f"Basic {encoded}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
