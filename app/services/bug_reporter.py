from app.core.models import Issue, BugTrackerType
from app.connectors.bug_tracker.jira import JiraConnector
from app.connectors.bug_tracker.azure_boards import AzureBoardsConnector
from app.connectors.bug_tracker.github_issues import GitHubIssuesConnector
from app.connectors.bug_tracker.linear import LinearConnector
from app.connectors.bug_tracker.base import BugTrackerConnector

TRACKER_MAP: dict[BugTrackerType, type[BugTrackerConnector]] = {
    BugTrackerType.JIRA: JiraConnector,
    BugTrackerType.AZURE_BOARDS: AzureBoardsConnector,
    BugTrackerType.GITHUB_ISSUES: GitHubIssuesConnector,
    BugTrackerType.LINEAR: LinearConnector,
}


def get_tracker(tracker_type: BugTrackerType) -> BugTrackerConnector:
    connector_cls = TRACKER_MAP.get(tracker_type)
    if not connector_cls:
        raise ValueError(f"Unsupported bug tracker: {tracker_type}")
    return connector_cls()


async def file_bugs(issues: list[Issue], tracker_type: BugTrackerType) -> list[dict]:
    if not issues:
        return []
    tracker = get_tracker(tracker_type)
    connected = await tracker.test_connection()
    if not connected:
        raise ConnectionError(f"Cannot connect to {tracker_type.value}. Check credentials.")
    return await tracker.file_bugs(issues)
