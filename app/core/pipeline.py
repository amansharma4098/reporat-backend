import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models import ScanRequest, ScanResult, ScanStatus, Issue, Severity
from app.services.repo_cloner import clone_repo, cleanup_repo
from app.services.test_runner import run_generated_tests
from app.analyzers.static import run_static_analysis
from app.analyzers.ai_testgen import generate_tests, analyze_failure
from anthropic import AsyncAnthropic
from app.core.config import settings

logger = logging.getLogger("reporat")

# In-memory scan store (kept for backward compat and WebSocket updates)
scan_store: dict[str, ScanResult] = {}

# Status update callbacks for WebSocket
_status_callbacks: dict[str, Callable] = {}


def register_callback(scan_id: str, callback: Callable):
    _status_callbacks[scan_id] = callback


def unregister_callback(scan_id: str):
    _status_callbacks.pop(scan_id, None)


async def _notify(scan_id: str, data: dict):
    cb = _status_callbacks.get(scan_id)
    if cb:
        try:
            await cb(data)
        except Exception:
            pass


async def _save_scan_to_db(scan: ScanResult, db: AsyncSession | None, scan_record_id: str | None):
    """Persist scan results to database if db session is available."""
    if not db or not scan_record_id:
        return
    try:
        from app.core.db_models import ScanRecord
        from sqlalchemy import update

        values = {
            "status": scan.status.value,
            "summary_json": json.dumps(scan.summary),
            "issues_json": json.dumps([i.model_dump() for i in scan.issues]),
            "test_results_json": json.dumps([t.model_dump() for t in scan.test_results]),
            "error": scan.error,
            "completed_at": scan.completed_at,
        }
        await db.execute(update(ScanRecord).where(ScanRecord.id == scan_record_id).values(**values))
        await db.commit()
    except Exception as e:
        logger.error(f"[{scan.scan_id}] Failed to save scan to DB: {e}")


async def run_scan(
    request: ScanRequest,
    scan_id: Optional[str] = None,
    db: AsyncSession | None = None,
    scan_record_id: str | None = None,
) -> ScanResult:
    scan = ScanResult(repo_url=request.repo_url)
    if scan_id:
        scan.scan_id = scan_id
    scan_store[scan.scan_id] = scan

    try:
        # Step 1: Clone
        scan.status = ScanStatus.CLONING
        await _notify(scan.scan_id, {"status": "cloning", "message": "Cloning repository..."})
        logger.info(f"[{scan.scan_id}] Cloning {request.repo_url}...")
        repo_path = await clone_repo(request.repo_url, request.branch, request.repo_source, scan.scan_id)

        # Step 2: Static Analysis
        if request.run_static_analysis:
            scan.status = ScanStatus.ANALYZING
            await _notify(scan.scan_id, {"status": "analyzing", "message": "Running static analysis..."})
            logger.info(f"[{scan.scan_id}] Running static analysis...")
            static_issues = await run_static_analysis(repo_path)
            scan.issues.extend(static_issues)
            await _notify(scan.scan_id, {
                "status": "analyzing",
                "message": f"Found {len(static_issues)} static analysis issues",
                "issues_count": len(static_issues),
            })

        # Step 3: AI Test Generation
        if request.run_ai_tests:
            scan.status = ScanStatus.GENERATING_TESTS
            await _notify(scan.scan_id, {"status": "generating_tests", "message": "Generating AI tests..."})
            logger.info(f"[{scan.scan_id}] Generating AI tests...")
            generated = await generate_tests(repo_path, request.include_patterns, request.exclude_patterns)
            scan.generated_tests = generated
            await _notify(scan.scan_id, {
                "status": "generating_tests",
                "message": f"Generated {len(generated)} test files",
                "tests_generated": len(generated),
            })

            # Step 4: Run Tests
            if generated:
                scan.status = ScanStatus.RUNNING_TESTS
                await _notify(scan.scan_id, {"status": "running_tests", "message": "Running generated tests..."})
                test_results = await run_generated_tests(repo_path, generated)
                scan.test_results = test_results

                failed = [r for r in test_results if not r.passed]
                if failed:
                    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
                    for result in failed:
                        error_text = result.error or result.output
                        ai_issue = await analyze_failure(client, error_text, "")
                        if ai_issue:
                            ai_issue.file_path = result.test_file
                            ai_issue.source = "test_failure"
                            scan.issues.append(ai_issue)

                await _notify(scan.scan_id, {
                    "status": "running_tests",
                    "message": f"Tests: {sum(1 for r in test_results if r.passed)} passed, {len(failed)} failed",
                    "tests_passed": sum(1 for r in test_results if r.passed),
                    "tests_failed": len(failed),
                })

        # Bug filing removed from pipeline — now triggered on-demand via API

        scan.status = ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        await _notify(scan.scan_id, {
            "status": "completed",
            "message": "Scan completed",
            "summary": scan.summary,
        })

    except Exception as e:
        scan.status = ScanStatus.FAILED
        scan.error = str(e)
        scan.completed_at = datetime.now(timezone.utc)
        await _notify(scan.scan_id, {"status": "failed", "message": str(e)})
        logger.error(f"[{scan.scan_id}] Scan failed: {e}")
    finally:
        cleanup_repo(scan.scan_id)
        unregister_callback(scan.scan_id)
        await _save_scan_to_db(scan, db, scan_record_id)

    return scan


def get_scan(scan_id: str) -> ScanResult | None:
    return scan_store.get(scan_id)


def get_all_scans() -> list[dict]:
    return [s.summary for s in sorted(scan_store.values(), key=lambda x: x.started_at, reverse=True)]
