import httpx
from app.connectors.bug_tracker.base import BugTrackerConnector
from app.core.models import Issue, Severity
from app.core.config import settings

SEVERITY_TO_PRIORITY = {
    Severity.CRITICAL: 1,
    Severity.HIGH: 2,
    Severity.MEDIUM: 3,
    Severity.LOW: 4,
    Severity.INFO: 4,
}


class LinearConnector(BugTrackerConnector):
    GRAPHQL_URL = "https://api.linear.app/graphql"

    def __init__(self, credentials: dict | None = None):
        if credentials:
            self.api_key = credentials["api_key"]
            self.team_id = credentials["team_id"]
        else:
            self.api_key = settings.linear_api_key
            self.team_id = settings.linear_team_id

    def _headers(self) -> dict:
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    async def file_bug(self, issue: Issue) -> dict:
        mutation = """
        mutation CreateIssue($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                success
                issue { id identifier title url }
            }
        }
        """
        desc = f"**Source:** {issue.source}\n**File:** `{issue.file_path}`"
        if issue.line_number:
            desc += f"\n**Line:** {issue.line_number}"
        desc += f"\n**Severity:** {issue.severity.value}\n\n{issue.description}"

        variables = {
            "input": {
                "teamId": self.team_id,
                "title": issue.title,
                "description": desc,
                "priority": SEVERITY_TO_PRIORITY.get(issue.severity, 3),
            }
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.GRAPHQL_URL,
                json={"query": mutation, "variables": variables},
                headers=self._headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            created = data["data"]["issueCreate"]["issue"]
            return {
                "tracker": "linear",
                "id": created["id"],
                "identifier": created["identifier"],
                "url": created["url"],
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
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.GRAPHQL_URL,
                    json={"query": "{ viewer { id name } }"},
                    headers=self._headers(),
                )
                return resp.status_code == 200
        except Exception:
            return False
