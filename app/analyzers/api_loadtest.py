import asyncio, httpx, time, statistics
from dataclasses import dataclass, field, asdict

@dataclass
class EndpointResult:
    url: str
    method: str
    avg_response_ms: float = 0
    min_response_ms: float = 0
    max_response_ms: float = 0
    p95_response_ms: float = 0
    p99_response_ms: float = 0
    total_requests: int = 0
    success_count: int = 0
    error_count: int = 0
    error_rate: float = 0
    throughput_rps: float = 0
    status_codes: dict = field(default_factory=dict)

@dataclass
class LoadTestResult:
    total_duration_s: float = 0
    total_requests: int = 0
    total_errors: int = 0
    avg_response_ms: float = 0
    p95_response_ms: float = 0
    throughput_rps: float = 0
    endpoints: list = field(default_factory=list)
    grade: str = "A"  # A/B/C/D/F based on response times and error rates

async def run_api_loadtest(base_url: str, endpoints: list[dict] = None, concurrent_users: int = 10, duration_seconds: int = 30, requests_per_user: int = 50) -> LoadTestResult:
    """
    Run load test against API endpoints.
    endpoints: [{"method": "GET", "path": "/api/health", "headers": {}, "body": None}, ...]
    If endpoints is None, auto-discover by hitting common paths.
    """
    if not endpoints:
        endpoints = [
            {"method": "GET", "path": "/", "headers": {}},
            {"method": "GET", "path": "/health", "headers": {}},
            {"method": "GET", "path": "/docs", "headers": {}},
        ]

    all_times = []
    endpoint_results = {}
    start = time.time()

    async def worker(client, ep):
        url = base_url.rstrip("/") + ep["path"]
        method = ep.get("method", "GET").upper()
        headers = ep.get("headers", {})
        body = ep.get("body")
        key = f"{method} {ep['path']}"

        if key not in endpoint_results:
            endpoint_results[key] = {"times": [], "errors": 0, "status_codes": {}, "url": url, "method": method}

        for _ in range(requests_per_user):
            t0 = time.time()
            try:
                if method == "GET":
                    r = await client.get(url, headers=headers, timeout=10)
                elif method == "POST":
                    r = await client.post(url, headers=headers, json=body, timeout=10)
                else:
                    r = await client.get(url, headers=headers, timeout=10)
                elapsed = (time.time() - t0) * 1000
                endpoint_results[key]["times"].append(elapsed)
                all_times.append(elapsed)
                sc = str(r.status_code)
                endpoint_results[key]["status_codes"][sc] = endpoint_results[key]["status_codes"].get(sc, 0) + 1
                if r.status_code >= 400:
                    endpoint_results[key]["errors"] += 1
            except Exception:
                elapsed = (time.time() - t0) * 1000
                endpoint_results[key]["times"].append(elapsed)
                endpoint_results[key]["errors"] += 1
                all_times.append(elapsed)

    async with httpx.AsyncClient() as client:
        tasks = []
        for ep in endpoints:
            for _ in range(concurrent_users):
                tasks.append(worker(client, ep))
        await asyncio.gather(*tasks)

    total_duration = time.time() - start

    # Build results
    ep_results = []
    for key, data in endpoint_results.items():
        times = sorted(data["times"]) if data["times"] else [0]
        total = len(times)
        ep_results.append(EndpointResult(
            url=data["url"], method=data["method"],
            avg_response_ms=round(statistics.mean(times), 1),
            min_response_ms=round(times[0], 1),
            max_response_ms=round(times[-1], 1),
            p95_response_ms=round(times[int(total * 0.95)] if total > 0 else 0, 1),
            p99_response_ms=round(times[int(total * 0.99)] if total > 0 else 0, 1),
            total_requests=total,
            success_count=total - data["errors"],
            error_count=data["errors"],
            error_rate=round(data["errors"] / total * 100, 1) if total > 0 else 0,
            throughput_rps=round(total / total_duration, 1),
            status_codes=data["status_codes"],
        ))

    sorted_all = sorted(all_times) if all_times else [0]
    total_reqs = len(all_times)
    avg = statistics.mean(all_times) if all_times else 0
    p95 = sorted_all[int(total_reqs * 0.95)] if total_reqs > 0 else 0
    error_total = sum(d["errors"] for d in endpoint_results.values())

    # Grade
    if avg < 200 and (error_total / max(total_reqs, 1)) < 0.01:
        grade = "A"
    elif avg < 500 and (error_total / max(total_reqs, 1)) < 0.05:
        grade = "B"
    elif avg < 1000 and (error_total / max(total_reqs, 1)) < 0.1:
        grade = "C"
    elif avg < 2000:
        grade = "D"
    else:
        grade = "F"

    return LoadTestResult(
        total_duration_s=round(total_duration, 1),
        total_requests=total_reqs,
        total_errors=error_total,
        avg_response_ms=round(avg, 1),
        p95_response_ms=round(p95, 1),
        throughput_rps=round(total_reqs / total_duration, 1),
        endpoints=[asdict(e) for e in ep_results],
        grade=grade,
    )
