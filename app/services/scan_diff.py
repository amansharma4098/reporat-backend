from app.core.models import Issue


def _issue_key(issue: dict | Issue) -> str:
    """Create composite key from file_path + title."""
    if isinstance(issue, Issue):
        return f"{issue.file_path}::{issue.title}"
    return f"{issue.get('file_path', '')}::{issue.get('title', '')}"


def compute_diff(current_issues: list, previous_issues: list) -> dict:
    """Compare current vs previous issues by (file_path, title) composite key."""
    current_keys = {_issue_key(i): i for i in current_issues}
    previous_keys = {_issue_key(i): i for i in previous_issues}

    current_set = set(current_keys.keys())
    previous_set = set(previous_keys.keys())

    new_keys = current_set - previous_set
    fixed_keys = previous_set - current_set
    unchanged_keys = current_set & previous_set

    def _to_dict(item):
        if isinstance(item, Issue):
            return item.model_dump()
        return item

    new_issues = [_to_dict(current_keys[k]) for k in new_keys]
    fixed_issues = [_to_dict(previous_keys[k]) for k in fixed_keys]
    unchanged = [_to_dict(current_keys[k]) for k in unchanged_keys]

    return {
        "new_issues": new_issues,
        "fixed_issues": fixed_issues,
        "unchanged": unchanged,
        "summary": f"{len(new_issues)} new, {len(fixed_issues)} fixed",
    }
