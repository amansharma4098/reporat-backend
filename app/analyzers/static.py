import asyncio
import json
import subprocess
from pathlib import Path
from app.core.models import Issue, Severity

RUFF_SEVERITY_MAP = {
    "E": Severity.MEDIUM, "W": Severity.LOW, "F": Severity.HIGH,
    "C": Severity.LOW, "I": Severity.INFO, "N": Severity.LOW,
    "S": Severity.HIGH, "B": Severity.MEDIUM,
}

BANDIT_SEVERITY_MAP = {
    "HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW,
}


async def run_ruff(repo_path: Path) -> list[Issue]:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: subprocess.run(
        ["ruff", "check", "--output-format=json", "--no-fix", str(repo_path)],
        capture_output=True, text=True,
    ))
    issues = []
    if result.stdout.strip():
        try:
            findings = json.loads(result.stdout)
        except json.JSONDecodeError:
            return issues
        for f in findings:
            code = f.get("code", "")
            prefix = code[0] if code else "E"
            severity = RUFF_SEVERITY_MAP.get(prefix, Severity.MEDIUM)
            rel_path = f.get("filename", "unknown")
            try:
                rel_path = str(Path(rel_path).relative_to(repo_path))
            except ValueError:
                pass
            issues.append(Issue(
                title=f"[Ruff {code}] {f.get('message', 'Linting issue')}",
                description=f"**Rule:** {code}\n**Message:** {f.get('message', '')}\n**Fix:** {f.get('fix', {}).get('message', 'N/A')}",
                file_path=rel_path,
                line_number=f.get("location", {}).get("row"),
                severity=severity,
                source="static_analysis",
                raw_output=json.dumps(f, indent=2),
            ))
    return issues


async def run_bandit(repo_path: Path) -> list[Issue]:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: subprocess.run(
        ["bandit", "-r", str(repo_path), "-f", "json", "-ll"],
        capture_output=True, text=True,
    ))
    issues = []
    if result.stdout.strip():
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return issues
        for r in data.get("results", []):
            severity = BANDIT_SEVERITY_MAP.get(r.get("issue_severity", "MEDIUM"), Severity.MEDIUM)
            rel_path = r.get("filename", "unknown")
            try:
                rel_path = str(Path(rel_path).relative_to(repo_path))
            except ValueError:
                pass
            issues.append(Issue(
                title=f"[Security] {r.get('issue_text', 'Security issue')}",
                description=f"**Test ID:** {r.get('test_id', 'N/A')}\n**Confidence:** {r.get('issue_confidence', 'N/A')}\n**Details:** {r.get('issue_text', '')}\n\n```\n{r.get('code', '')}\n```",
                file_path=rel_path,
                line_number=r.get("line_number"),
                severity=severity,
                source="static_analysis",
                raw_output=json.dumps(r, indent=2),
            ))
    return issues


async def run_static_analysis(repo_path: Path) -> list[Issue]:
    ruff_issues, bandit_issues = await asyncio.gather(
        run_ruff(repo_path), run_bandit(repo_path)
    )
    return ruff_issues + bandit_issues
