import logging
import httpx

logger = logging.getLogger("reporat.notifications")


async def send_slack(webhook_url: str, scan_result: dict):
    """Send scan result as Slack Block Kit message."""
    summary = scan_result.get("summary") or scan_result
    repo = summary.get("repo_url", "Unknown repo")
    status = summary.get("status", "unknown")
    total_issues = summary.get("total_issues", 0)
    by_severity = summary.get("by_severity", {})
    tests_passed = summary.get("tests_passed", 0)
    tests_failed = summary.get("tests_failed", 0)

    status_emoji = ":white_check_mark:" if status == "completed" else ":x:"
    severity_text = " | ".join(f"*{k.title()}:* {v}" for k, v in by_severity.items() if v > 0) or "None"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{status_emoji} RepoRat Scan {status.title()}", "emoji": True},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Repository:*\n{repo}"},
                {"type": "mrkdwn", "text": f"*Status:*\n{status.title()}"},
                {"type": "mrkdwn", "text": f"*Issues Found:*\n{total_issues}"},
                {"type": "mrkdwn", "text": f"*Tests:*\n{tests_passed} passed, {tests_failed} failed"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Severity Breakdown:*\n{severity_text}"},
        },
    ]

    payload = {"blocks": blocks, "text": f"RepoRat Scan {status.title()}: {repo}"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()


async def send_discord(webhook_url: str, scan_result: dict):
    """Send scan result as Discord embed."""
    summary = scan_result.get("summary") or scan_result
    repo = summary.get("repo_url", "Unknown repo")
    status = summary.get("status", "unknown")
    total_issues = summary.get("total_issues", 0)
    by_severity = summary.get("by_severity", {})
    tests_passed = summary.get("tests_passed", 0)
    tests_failed = summary.get("tests_failed", 0)

    color = 0x00FF00 if status == "completed" else 0xFF0000
    severity_text = " | ".join(f"**{k.title()}:** {v}" for k, v in by_severity.items() if v > 0) or "None"

    embed = {
        "title": f"RepoRat Scan {status.title()}",
        "color": color,
        "fields": [
            {"name": "Repository", "value": repo, "inline": False},
            {"name": "Issues Found", "value": str(total_issues), "inline": True},
            {"name": "Tests", "value": f"{tests_passed} passed, {tests_failed} failed", "inline": True},
            {"name": "Severity Breakdown", "value": severity_text, "inline": False},
        ],
    }

    payload = {"embeds": [embed]}

    async with httpx.AsyncClient() as client:
        resp = await client.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()


async def send_notification(notif_type: str, webhook_url: str, scan_result: dict):
    """Dispatch notification by type."""
    if notif_type == "slack":
        await send_slack(webhook_url, scan_result)
    elif notif_type == "discord":
        await send_discord(webhook_url, scan_result)
