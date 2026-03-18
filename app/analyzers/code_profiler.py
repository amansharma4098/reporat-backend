import re

def analyze_code_for_performance(source_code: str, file_path: str) -> list[dict]:
    """Static analysis for performance anti-patterns and potential memory leaks."""
    issues = []
    lines = source_code.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Large list in memory
        if re.search(r'=\s*\[.*for\s+\w+\s+in\s+', stripped) and "[::" not in stripped:
            issues.append({
                "severity": "medium",
                "title": "List comprehension may consume excessive memory",
                "description": "Consider using a generator expression instead of list comprehension for large datasets.",
                "file_path": file_path,
                "line_number": i,
            })

        # Global mutable state
        if re.match(r'^[A-Z_]+\s*[:=]\s*(\[|\{|dict|list|set)', stripped) and "Final" not in stripped:
            issues.append({
                "severity": "medium",
                "title": "Global mutable state detected",
                "description": "Mutable global variables can cause memory leaks and race conditions in concurrent environments.",
                "file_path": file_path,
                "line_number": i,
            })

        # Sleep in async
        if "time.sleep(" in stripped:
            issues.append({
                "severity": "high",
                "title": "Blocking sleep in potentially async code",
                "description": "time.sleep() blocks the event loop. Use asyncio.sleep() instead.",
                "file_path": file_path,
                "line_number": i,
            })

        # Unbounded cache
        if "@lru_cache" in stripped and "maxsize" not in stripped:
            issues.append({
                "severity": "medium",
                "title": "Unbounded LRU cache",
                "description": "lru_cache without maxsize can grow indefinitely. Set maxsize to prevent memory leaks.",
                "file_path": file_path,
                "line_number": i,
            })

        # String concatenation in loop
        if "+=" in stripped and ('""' in stripped or "''" in stripped or "str" in stripped):
            issues.append({
                "severity": "low",
                "title": "String concatenation in loop",
                "description": "Repeated string concatenation is O(n²). Use list.append() + ''.join() instead.",
                "file_path": file_path,
                "line_number": i,
            })

        # Synchronous file I/O in async
        if any(p in stripped for p in ["open(", "os.read", "os.write", "shutil."]) and "aiofiles" not in stripped:
            issues.append({
                "severity": "medium",
                "title": "Synchronous I/O in potentially async context",
                "description": "Use aiofiles for async file operations to avoid blocking the event loop.",
                "file_path": file_path,
                "line_number": i,
            })

        # Recursive function without limit
        if re.match(r'def\s+(\w+)', stripped):
            func_name = re.match(r'def\s+(\w+)', stripped).group(1)
            # Check if function calls itself in next 20 lines
            for j in range(i, min(i + 20, len(lines))):
                if func_name + "(" in lines[j - 1] and j != i:
                    issues.append({
                        "severity": "medium",
                        "title": f"Recursive function '{func_name}' without depth limit",
                        "description": "Recursive functions can cause stack overflow. Add a max depth parameter or use sys.setrecursionlimit().",
                        "file_path": file_path,
                        "line_number": i,
                    })
                    break

    return issues
