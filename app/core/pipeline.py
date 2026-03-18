import json
import logging
import os
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


async def _send_notifications(scan: ScanResult, db: AsyncSession | None, scan_record_id: str | None):
    """Send notifications after scan completes. Never fail the scan."""
    if not db or not scan_record_id:
        return
    try:
        from app.core.db_models import ScanRecord, NotificationConfig
        from app.services.notifications import send_notification
        from sqlalchemy import select

        # Get tenant_id from scan record
        rec_result = await db.execute(
            select(ScanRecord.tenant_id).where(ScanRecord.id == scan_record_id)
        )
        row = rec_result.first()
        if not row:
            return
        tenant_id = row[0]

        # Get enabled notification configs
        result = await db.execute(
            select(NotificationConfig).where(
                NotificationConfig.tenant_id == tenant_id,
                NotificationConfig.enabled == True,
            )
        )
        configs = result.scalars().all()

        scan_data = {"summary": scan.summary}
        for config in configs:
            # Check notify_on filter
            if config.notify_on == "failed" and scan.status.value != "failed":
                continue
            if config.notify_on == "critical_only":
                has_critical = any(i.severity.value == "critical" for i in scan.issues)
                if not has_critical:
                    continue
            try:
                await send_notification(config.type, config.webhook_url, scan_data)
            except Exception as e:
                logger.warning(f"[{scan.scan_id}] Notification ({config.type}) failed: {e}")
    except Exception as e:
        logger.warning(f"[{scan.scan_id}] Notification dispatch error: {e}")


async def _save_scan_to_db(scan: ScanResult, db: AsyncSession | None, scan_record_id: str | None):
    """Persist scan results to database if db session is available."""
    if not db or not scan_record_id:
        return
    try:
        from app.core.db_models import ScanRecord
        from sqlalchemy import update

        summary_json = json.dumps(scan.summary) if scan.summary else "{}"
        issues_json = json.dumps([i.model_dump() for i in scan.issues]) if scan.issues else "[]"
        test_results_json = json.dumps([t.model_dump() for t in scan.test_results]) if scan.test_results else "[]"

        values = {
            "status": scan.status.value,
            "summary_json": summary_json,
            "issues_json": issues_json,
            "test_results_json": test_results_json,
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
        print(f"[{scan.scan_id}] Step 1: Cloning repo...")
        scan.status = ScanStatus.CLONING
        await _notify(scan.scan_id, {"status": "cloning", "message": "Cloning repository..."})
        logger.info(f"[{scan.scan_id}] Cloning {request.repo_url}...")
        repo_path = await clone_repo(request.repo_url, request.branch, request.repo_source, scan.scan_id)

        # Verify clone succeeded
        if repo_path is None or not repo_path.is_dir():
            raise RuntimeError(f"Clone failed: repo_path is {'None' if repo_path is None else 'not a directory'}")
        print(f"[{scan.scan_id}] Step 1 complete: Cloned to {repo_path}")

        # Step 2: Static Analysis
        if request.run_static_analysis:
            print(f"[{scan.scan_id}] Step 2: Running static analysis...")
            scan.status = ScanStatus.ANALYZING
            await _notify(scan.scan_id, {"status": "analyzing", "message": "Running static analysis..."})
            logger.info(f"[{scan.scan_id}] Running static analysis...")
            static_issues = await run_static_analysis(repo_path)
            if static_issues is not None:
                scan.issues.extend(static_issues)
            else:
                print(f"[{scan.scan_id}] Warning: static analysis returned None")
            await _notify(scan.scan_id, {
                "status": "analyzing",
                "message": f"Found {len(static_issues) if static_issues else 0} static analysis issues",
                "issues_count": len(static_issues) if static_issues else 0,
            })
            print(f"[{scan.scan_id}] Step 2 complete: {len(static_issues) if static_issues else 0} issues found")

        # Step 2b: Performance & DB analysis
        print(f"[{scan.scan_id}] Step 2b: Running performance/DB analysis...")
        from app.analyzers.db_analyzer import analyze_code_for_db_issues
        from app.analyzers.code_profiler import analyze_code_for_performance
        perf_db_count = 0
        try:
            for py_file in repo_path.rglob("*.py"):
                try:
                    source = py_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                rel_path = str(py_file.relative_to(repo_path))
                db_issues = analyze_code_for_db_issues(source, rel_path)
                perf_issues = analyze_code_for_performance(source, rel_path)
                for raw in db_issues:
                    scan.issues.append(Issue(
                        title=raw["title"],
                        description=raw["description"],
                        file_path=raw["file_path"],
                        line_number=raw.get("line_number"),
                        severity=Severity(raw.get("severity", "medium")),
                        source="database",
                    ))
                    perf_db_count += 1
                for raw in perf_issues:
                    scan.issues.append(Issue(
                        title=raw["title"],
                        description=raw["description"],
                        file_path=raw["file_path"],
                        line_number=raw.get("line_number"),
                        severity=Severity(raw.get("severity", "medium")),
                        source="performance",
                    ))
                    perf_db_count += 1
        except Exception as e:
            print(f"[{scan.scan_id}] Warning: performance/DB analysis error: {e}")
        print(f"[{scan.scan_id}] Step 2b: {perf_db_count} performance/db issues found")

        # Step 3: AI Test Generation
        if request.run_ai_tests:
            print(f"[{scan.scan_id}] Step 3: Generating AI tests...")
            scan.status = ScanStatus.GENERATING_TESTS
            await _notify(scan.scan_id, {"status": "generating_tests", "message": "Generating AI tests..."})
            logger.info(f"[{scan.scan_id}] Generating AI tests...")
            generated = await generate_tests(repo_path, request.include_patterns, request.exclude_patterns)
            if generated is not None:
                scan.generated_tests = generated
            else:
                generated = []
                print(f"[{scan.scan_id}] Warning: generate_tests returned None")
            await _notify(scan.scan_id, {
                "status": "generating_tests",
                "message": f"Generated {len(generated)} test files",
                "tests_generated": len(generated),
            })
            print(f"[{scan.scan_id}] Step 3 complete: {len(generated)} tests generated")

            # Step 4: Run Tests
            if generated:
                print(f"[{scan.scan_id}] Step 4: Running generated tests...")
                scan.status = ScanStatus.RUNNING_TESTS
                await _notify(scan.scan_id, {"status": "running_tests", "message": "Running generated tests..."})
                test_results = await run_generated_tests(repo_path, generated)
                if test_results is not None:
                    scan.test_results = test_results
                else:
                    test_results = []
                    print(f"[{scan.scan_id}] Warning: run_generated_tests returned None")

                failed = [r for r in test_results if not r.passed]
                if failed:
                    try:
                        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
                        for result in failed:
                            error_text = result.error or result.output
                            ai_issue = await analyze_failure(client, error_text, "")
                            if ai_issue is not None:
                                ai_issue.file_path = result.test_file
                                ai_issue.source = "test_failure"
                                scan.issues.append(ai_issue)
                    except Exception as e:
                        print(f"[{scan.scan_id}] Warning: failure analysis error: {e}")

                await _notify(scan.scan_id, {
                    "status": "running_tests",
                    "message": f"Tests: {sum(1 for r in test_results if r.passed)} passed, {len(failed)} failed",
                    "tests_passed": sum(1 for r in test_results if r.passed),
                    "tests_failed": len(failed),
                })
                print(f"[{scan.scan_id}] Step 4 complete: {sum(1 for r in test_results if r.passed)} passed, {len(failed)} failed")

        # Bug filing removed from pipeline — now triggered on-demand via API

        scan.status = ScanStatus.COMPLETED
        scan.completed_at = datetime.now(timezone.utc)
        await _notify(scan.scan_id, {
            "status": "completed",
            "message": "Scan completed",
            "summary": scan.summary,
        })
        print(f"[{scan.scan_id}] Step 5: Scan complete. {len(scan.issues)} issues found.")

    except Exception as e:
        scan.status = ScanStatus.FAILED
        scan.error = str(e)
        scan.completed_at = datetime.now(timezone.utc)
        await _notify(scan.scan_id, {"status": "failed", "message": str(e)})
        logger.error(f"[{scan.scan_id}] Scan failed: {e}", exc_info=True)
        print(f"[{scan.scan_id}] SCAN FAILED: {e}")
    finally:
        cleanup_repo(scan.scan_id)
        unregister_callback(scan.scan_id)
        await _save_scan_to_db(scan, db, scan_record_id)
        await _send_notifications(scan, db, scan_record_id)

    return scan


def get_scan(scan_id: str) -> ScanResult | None:
    return scan_store.get(scan_id)


def get_all_scans() -> list[dict]:
    return [s.summary for s in sorted(scan_store.values(), key=lambda x: x.started_at, reverse=True)]
