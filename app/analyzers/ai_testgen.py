import asyncio
from pathlib import Path
from anthropic import AsyncAnthropic
from app.core.config import settings
from app.core.models import GeneratedTest, Issue, Severity

SUPPORTED_EXTENSIONS = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".jsx": "javascript", ".tsx": "typescript",
}

SYSTEM_PROMPT = """You are an expert software testing engineer. Given source code, generate comprehensive unit tests that:
1. Cover all public functions/methods
2. Test edge cases (null, empty, boundary values)
3. Test error handling paths
4. Use standard testing frameworks (pytest for Python, jest for JS/TS)
5. Include descriptive test names

Respond ONLY with the test code. No explanation, no markdown fences."""


def _detect_language(file_path: str) -> str | None:
    return SUPPORTED_EXTENSIONS.get(Path(file_path).suffix.lower())


def _should_test(file_path: Path, exclude_patterns: list[str]) -> bool:
    path_str = str(file_path)
    for pattern in exclude_patterns:
        if pattern in path_str:
            return False
    if file_path.name.startswith("__"):
        return False
    if "test" in file_path.name.lower() or "spec" in file_path.name.lower():
        return False
    return True


async def generate_tests_for_file(
    client: AsyncAnthropic, file_path: Path, repo_path: Path,
) -> GeneratedTest | None:
    language = _detect_language(str(file_path))
    if not language:
        return None
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    if len(source.strip()) < 50:
        return None
    if len(source) > 15000:
        source = source[:15000] + "\n# ... (truncated)"

    rel_path = str(file_path.relative_to(repo_path))
    prompt = f"""Generate unit tests for this {language} file.

File: {rel_path}

```{language}
{source}
```

Generate comprehensive tests using {'pytest' if language == 'python' else 'jest'}."""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        test_code = response.content[0].text.strip()
        if test_code.startswith("```"):
            lines = test_code.split("\n")
            test_code = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        ext = ".py" if language == "python" else ".test.js" if language == "javascript" else ".test.ts"
        return GeneratedTest(
            file_path=f"test_{file_path.stem}{ext}",
            test_code=test_code,
            target_file=rel_path,
            language=language,
        )
    except Exception as e:
        print(f"[AI TestGen] Error for {rel_path}: {e}")
        return None


async def generate_tests(
    repo_path: Path, include_patterns: list[str], exclude_patterns: list[str], max_files: int = 20,
) -> list[GeneratedTest]:
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    eligible = []
    for pattern in include_patterns:
        for fp in repo_path.rglob(pattern):
            if fp.is_file() and _should_test(fp, exclude_patterns):
                eligible.append(fp)
    eligible = eligible[:max_files]

    tests = []
    for i in range(0, len(eligible), 5):
        batch = eligible[i:i + 5]
        results = await asyncio.gather(
            *[generate_tests_for_file(client, f, repo_path) for f in batch],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, GeneratedTest):
                tests.append(r)
    return tests


async def analyze_failure(client: AsyncAnthropic, test_output: str, source_code: str) -> Issue | None:
    prompt = f"""Analyze this test failure and create a concise bug report.

Test Output:
```
{test_output[:3000]}
```

Source Code:
```
{source_code[:5000]}
```

Respond in this exact format:
TITLE: <one-line bug title>
SEVERITY: <critical|high|medium|low>
DESCRIPTION: <2-3 sentence description of root cause and fix>"""

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        title, severity, description = "", Severity.MEDIUM, ""
        for line in text.split("\n"):
            if line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("SEVERITY:"):
                sev = line.replace("SEVERITY:", "").strip().lower()
                severity = Severity(sev) if sev in [s.value for s in Severity] else Severity.MEDIUM
            elif line.startswith("DESCRIPTION:"):
                description = line.replace("DESCRIPTION:", "").strip()
        if title:
            return Issue(
                title=title, description=description, file_path="",
                severity=severity, source="ai_test",
            )
    except Exception as e:
        print(f"[AI TestGen] Failure analysis error: {e}")
    return None
