import asyncio
import subprocess
from pathlib import Path
from app.core.models import GeneratedTest, TestResult


async def run_python_test(test_path: Path) -> TestResult:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            ["python", "-m", "pytest", str(test_path), "-v", "--tb=short", "--no-header"],
            capture_output=True, text=True, timeout=60,
        ))
    except subprocess.TimeoutExpired:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error="Timed out (60s)",
        )
    except Exception as e:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error=f"Subprocess error: {e}",
        )

    if result is None:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error="Subprocess returned None",
        )

    return TestResult(
        test_file=test_path.name, passed=result.returncode == 0,
        output=result.stdout or "", error=result.stderr if result.returncode != 0 else None,
    )


async def run_js_test(test_path: Path) -> TestResult:
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            ["npx", "jest", str(test_path), "--no-coverage", "--verbose"],
            capture_output=True, text=True, timeout=60, cwd=str(test_path.parent),
        ))
    except subprocess.TimeoutExpired:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error="Timed out (60s)",
        )
    except Exception as e:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error=f"Subprocess error: {e}",
        )

    if result is None:
        return TestResult(
            test_file=test_path.name, passed=False, output="", error="Subprocess returned None",
        )

    return TestResult(
        test_file=test_path.name, passed=result.returncode == 0,
        output=result.stdout or "", error=result.stderr if result.returncode != 0 else None,
    )


async def run_generated_tests(repo_path: Path, generated_tests: list[GeneratedTest]) -> list[TestResult]:
    test_dir = repo_path / "_reporat_tests"
    test_dir.mkdir(exist_ok=True)
    results = []

    for gt in generated_tests:
        test_path = test_dir / gt.file_path
        test_path.write_text(gt.test_code, encoding="utf-8")
        try:
            if gt.language == "python":
                result = await run_python_test(test_path)
            elif gt.language in ("javascript", "typescript"):
                result = await run_js_test(test_path)
            else:
                continue
            results.append(result)
        except subprocess.TimeoutExpired:
            results.append(TestResult(
                test_file=gt.file_path, passed=False, output="", error="Timed out (60s)",
            ))
        except Exception as e:
            results.append(TestResult(
                test_file=gt.file_path, passed=False, output="", error=str(e),
            ))
    return results
