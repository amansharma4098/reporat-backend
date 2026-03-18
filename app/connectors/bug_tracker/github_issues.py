import httpx
from app.connectors.bug_tracker.base import BugTrackerConnector
from app.core.models import Issue, Severity
from app.core.config import settings

SEVERITY_LABELS = {
    Severity.CRITICAL: ["bug", "critical", "reporat"],
    Severity.HIGH: ["bug", "high-priority", "reporat"],
    Severity.MEDIUM: ["bug", "reporat"],
    Severity.LOW: ["bug", "low-priority", "reporat"],
    Severity.INFO: ["info", "reporat"],
}


class GitHubIssuesConnector(BugTrackerConnector):
    def __init__(self, credentials: dict | None = None):
        if credentials:
            self.pat = credentials["pat"]
            self.repo = credentials["repo"]
        else:
            self.pat = settings.github_issues_pat
            self.repo = settings.github_issues_repo
        self.base_url = f"https://api.github.com/repos/{self.repo}"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _build_payload(self, issue: Issue) -> dict:
        body = f"**Source:** {issue.source}\n**File:** `{issue.file_path}`\n"
        if issue.line_number:
            body += f"**Line:** {issue.line_number}\n"
        body += f"**Severity:** {issue.severity.value}\n\n---\n\n{issue.description}"
        if issue.raw_output:
            body += f"\n\n<details><summary>Raw Output</summary>\n\n```\n{issue.raw_output}\n```\n</details>"
        return {
            "title": issue.title,
            "body": body,
            "labels": SEVERITY_LABELS.get(issue.severity, ["bug", "reporat"]),
        }

    async def file_bug(self, issue: Issue) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/issues",
                json=self._build_payload(issue),
                headers=self._headers(),
            )
            if resp.status_code == 403:
                raise PermissionError(
                    f"GitHub API returned 403 for {self.repo}. "
                    "Ensure the token has 'issues: write' permission (fine-grained PAT) "
                    "or 'repo' scope (classic PAT)."
                )
            if resp.status_code == 404:
                raise ValueError(
                    f"Repository '{self.repo}' not found or not accessible with the provided token."
                )
            resp.raise_for_status()
            data = resp.json()
            return {
                "tracker": "github_issues",
                "number": data["number"],
                "url": data["html_url"],
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
                resp = await client.get(self.base_url, headers=self._headers())
                if resp.status_code == 403:
                    raise PermissionError(
                        f"GitHub API returned 403. Check that your token has access to '{self.repo}'."
                    )
                return resp.status_code == 200
        except PermissionError:
            raise
        except Exception:
            return False
