from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum
from datetime import datetime
import uuid


class RepoSource(str, Enum):
    GITHUB = "github"
    AZURE_DEVOPS = "azure_devops"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"


class BugTrackerType(str, Enum):
    JIRA = "jira"
    AZURE_BOARDS = "azure_boards"
    GITHUB_ISSUES = "github_issues"
    LINEAR = "linear"


class ScanStatus(str, Enum):
    PENDING = "pending"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    GENERATING_TESTS = "generating_tests"
    RUNNING_TESTS = "running_tests"
    FILING_BUGS = "filing_bugs"
    COMPLETED = "completed"
    FAILED = "failed"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# --- Request Models ---

class ScanRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    repo_source: RepoSource = RepoSource.GITHUB
    bug_tracker: BugTrackerType = BugTrackerType.GITHUB_ISSUES
    run_static_analysis: bool = True
    run_ai_tests: bool = True
    file_bugs: bool = True
    include_patterns: list[str] = Field(default_factory=lambda: ["*.py", "*.js", "*.ts"])
    exclude_patterns: list[str] = Field(default_factory=lambda: ["node_modules", ".git", "__pycache__", "venv"])


class ConnectorConfig(BaseModel):
    type: str
    credentials: dict


# --- Issue / Bug Models ---

class Issue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    severity: Severity = Severity.MEDIUM
    source: Literal["static_analysis", "ai_test", "test_failure"] = "static_analysis"
    raw_output: Optional[str] = None


class GeneratedTest(BaseModel):
    file_path: str
    test_code: str
    target_file: str
    language: str


class TestResult(BaseModel):
    test_file: str
    passed: bool
    output: str
    error: Optional[str] = None
    duration_ms: Optional[float] = None


# --- Scan Result ---

class ScanResult(BaseModel):
    scan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    repo_url: str
    status: ScanStatus = ScanStatus.PENDING
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    issues: list[Issue] = Field(default_factory=list)
    generated_tests: list[GeneratedTest] = Field(default_factory=list)
    test_results: list[TestResult] = Field(default_factory=list)
    bugs_filed: list[dict] = Field(default_factory=list)
    error: Optional[str] = None

    @property
    def summary(self) -> dict:
        return {
            "scan_id": self.scan_id,
            "repo_url": self.repo_url,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_issues": len(self.issues),
            "tests_generated": len(self.generated_tests),
            "tests_passed": sum(1 for t in self.test_results if t.passed),
            "tests_failed": sum(1 for t in self.test_results if not t.passed),
            "bugs_filed": len(self.bugs_filed),
            "by_severity": {
                s.value: sum(1 for i in self.issues if i.severity == s)
                for s in Severity
            },
        }
