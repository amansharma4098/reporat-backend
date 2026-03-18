import asyncio, httpx, time, re

async def analyze_frontend_performance(url: str) -> dict:
    """Analyze frontend performance metrics by loading the page."""
    results = {
        "url": url,
        "load_time_ms": 0,
        "ttfb_ms": 0,
        "page_size_kb": 0,
        "resource_count": 0,
        "has_gzip": False,
        "has_cache_headers": False,
        "has_https": url.startswith("https"),
        "html_size_kb": 0,
        "issues": [],
        "score": 100,
        "grade": "A",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            t0 = time.time()
            r = await client.get(url, timeout=30)
            load_time = (time.time() - t0) * 1000

            results["load_time_ms"] = round(load_time, 1)
            results["ttfb_ms"] = round(load_time, 1)  # Simplified
            results["page_size_kb"] = round(len(r.content) / 1024, 1)
            results["html_size_kb"] = round(len(r.content) / 1024, 1)
            results["has_gzip"] = "gzip" in r.headers.get("content-encoding", "")
            results["has_cache_headers"] = "cache-control" in r.headers

            html = r.text

            # Count resources
            scripts = len(re.findall(r'<script[^>]+src=', html))
            styles = len(re.findall(r'<link[^>]+stylesheet', html))
            images = len(re.findall(r'<img[^>]+src=', html))
            results["resource_count"] = scripts + styles + images

            # Check for common issues
            score = 100

            if load_time > 3000:
                results["issues"].append({"severity": "critical", "title": "Slow page load", "description": f"Page took {round(load_time)}ms to load. Target: under 3000ms."})
                score -= 30
            elif load_time > 1000:
                results["issues"].append({"severity": "medium", "title": "Page load could be faster", "description": f"Page took {round(load_time)}ms. Target: under 1000ms."})
                score -= 10

            if results["html_size_kb"] > 500:
                results["issues"].append({"severity": "high", "title": "Large HTML payload", "description": f"HTML is {results['html_size_kb']}KB. Consider lazy loading."})
                score -= 15

            if not results["has_gzip"]:
                results["issues"].append({"severity": "medium", "title": "No gzip compression", "description": "Enable gzip/brotli compression to reduce transfer size."})
                score -= 10

            if not results["has_cache_headers"]:
                results["issues"].append({"severity": "low", "title": "Missing cache headers", "description": "Add Cache-Control headers for static assets."})
                score -= 5

            if scripts > 10:
                results["issues"].append({"severity": "medium", "title": f"Too many scripts ({scripts})", "description": "Bundle scripts to reduce HTTP requests."})
                score -= 10

            if not results["has_https"]:
                results["issues"].append({"severity": "critical", "title": "No HTTPS", "description": "Site is not using HTTPS. This is a security risk."})
                score -= 20

            # Check meta tags
            if '<meta name="viewport"' not in html:
                results["issues"].append({"severity": "medium", "title": "Missing viewport meta", "description": "Add viewport meta tag for mobile responsiveness."})
                score -= 5

            if '<meta name="description"' not in html:
                results["issues"].append({"severity": "low", "title": "Missing meta description", "description": "Add meta description for SEO."})
                score -= 3

            results["score"] = max(0, score)
            if score >= 90: results["grade"] = "A"
            elif score >= 70: results["grade"] = "B"
            elif score >= 50: results["grade"] = "C"
            elif score >= 30: results["grade"] = "D"
            else: results["grade"] = "F"

    except Exception as e:
        results["issues"].append({"severity": "critical", "title": "Failed to load page", "description": str(e)})
        results["score"] = 0
        results["grade"] = "F"

    return results
