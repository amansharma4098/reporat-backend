import httpx
from app.connectors.bug_tracker.base import BugTrackerConnector
from app.core.models import Issue, Severity
from app.core.config import settings

SEVERITY_TO_PRIORITY = {
    Severity.CRITICAL: "Highest",
    Severity.HIGH: "High",
    Severity.MEDIUM: "Medium",
    Severity.LOW: "Low",
    Severity.INFO: "Lowest",
}


class JiraConnector(BugTrackerConnector):
    def __init__(self, credentials: dict | None = None):
        if credentials:
            self.base_url = credentials["url"].rstrip("/")
            self.auth = (credentials["email"], credentials["api_token"])
            self.project_key = credentials["project_key"]
        else:
            self.base_url = settings.jira_url.rstrip("/")
            self.auth = (settings.jira_email, settings.jira_api_token)
            self.project_key = settings.jira_project_key

    def _headers(self) -> dict:
        return {"Content-Type": "application/json", "Accept": "application/json"}

    def _build_payload(self, issue: Issue) -> dict:
        return {
            "fields": {
                "project": {"key": self.project_key},
                "summary": issue.title,
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": issue.description}],
                        }
                    ],
                },
                "issuetype": {"name": "Bug"},
                "priority": {"name": SEVERITY_TO_PRIORITY.get(issue.severity, "Medium")},
                "labels": ["reporat", issue.source],
            }
        }

    async def file_bug(self, issue: Issue) -> dict:
        async with httpx.AsyncClient(auth=self.auth) as client:
            resp = await client.post(
                f"{self.base_url}/rest/api/3/issue",
                json=self._build_payload(issue),
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                "tracker": "jira",
                "key": data["key"],
                "url": f"{self.base_url}/browse/{data['key']}",
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
            async with httpx.AsyncClient(auth=self.auth) as client:
                resp = await client.get(
                    f"{self.base_url}/rest/api/3/myself", headers=self._headers()
                )
                return resp.status_code == 200
        except Exception:
            return False
