import re

def analyze_code_for_db_issues(source_code: str, file_path: str) -> list[dict]:
    """Static analysis for common database anti-patterns."""
    issues = []
    lines = source_code.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # N+1 detection: query inside a loop
        if re.search(r'for\s+\w+\s+in\s+', stripped):
            # Check next 5 lines for query patterns
            for j in range(i, min(i + 5, len(lines))):
                next_line = lines[j - 1].strip() if j <= len(lines) else ""
                if any(p in next_line for p in [".query(", ".filter(", ".execute(", "select(", "SELECT ", "await db.", ".all()", ".first()"]):
                    issues.append({
                        "severity": "high",
                        "title": f"Potential N+1 query in loop",
                        "description": f"Database query detected inside a loop at line {j}. This causes N+1 queries. Use eager loading (joinedload/selectinload) or batch queries.",
                        "file_path": file_path,
                        "line_number": j,
                    })

        # Missing index hints
        if ".filter(" in stripped or ".where(" in stripped:
            if "id" not in stripped.lower() and "pk" not in stripped.lower():
                issues.append({
                    "severity": "medium",
                    "title": "Query may need an index",
                    "description": f"Filtering on a non-primary-key column. Ensure the filtered column has a database index.",
                    "file_path": file_path,
                    "line_number": i,
                })

        # Raw SQL detection
        if re.search(r'(execute|raw|text)\s*\(\s*[f"\'].*SELECT|INSERT|UPDATE|DELETE', stripped, re.IGNORECASE):
            issues.append({
                "severity": "medium",
                "title": "Raw SQL query detected",
                "description": "Using raw SQL instead of ORM. This may be vulnerable to SQL injection if not parameterized.",
                "file_path": file_path,
                "line_number": i,
            })

        # Missing pagination
        if (".all()" in stripped or ".fetchall()" in stripped) and "limit" not in stripped.lower() and "paginate" not in stripped.lower():
            issues.append({
                "severity": "medium",
                "title": "Unbounded query — missing pagination",
                "description": "Fetching all rows without LIMIT. This can cause memory issues with large datasets.",
                "file_path": file_path,
                "line_number": i,
            })

        # Lazy loading in async context
        if "relationship(" in stripped and "lazy=" not in stripped:
            issues.append({
                "severity": "low",
                "title": "Relationship without explicit lazy strategy",
                "description": "SQLAlchemy relationship without lazy= parameter. In async context, use lazy='selectin' or 'joined'.",
                "file_path": file_path,
                "line_number": i,
            })

    return issues
