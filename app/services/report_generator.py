import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


def generate_pdf(scan_data: dict) -> bytes:
    """Generate a PDF report from scan result data."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("CustomTitle", parent=styles["Title"], fontSize=20, spaceAfter=12)
    heading_style = ParagraphStyle("CustomHeading", parent=styles["Heading2"], fontSize=14, spaceAfter=8)

    elements = []

    # Title
    elements.append(Paragraph("RepoRat Scan Report", title_style))
    elements.append(Spacer(1, 6 * mm))

    # Scan metadata
    summary = scan_data.get("summary") or scan_data
    meta_data = [
        ["Repository", summary.get("repo_url", "N/A")],
        ["Status", summary.get("status", "N/A")],
        ["Started", summary.get("started_at", "N/A")],
        ["Completed", summary.get("completed_at", "N/A")],
        ["Total Issues", str(summary.get("total_issues", 0))],
    ]
    meta_table = Table(meta_data, colWidths=[120, 350])
    meta_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 8 * mm))

    # Severity breakdown
    by_severity = summary.get("by_severity", {})
    if by_severity:
        elements.append(Paragraph("Severity Breakdown", heading_style))
        sev_data = [["Severity", "Count"]]
        severity_colors = {
            "critical": colors.HexColor("#dc2626"),
            "high": colors.HexColor("#ea580c"),
            "medium": colors.HexColor("#ca8a04"),
            "low": colors.HexColor("#2563eb"),
            "info": colors.HexColor("#6b7280"),
        }
        for sev, count in by_severity.items():
            sev_data.append([sev.title(), str(count)])

        sev_table = Table(sev_data, colWidths=[120, 80])
        sev_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]
        for i, sev in enumerate(by_severity.keys()):
            if sev in severity_colors:
                sev_style.append(("TEXTCOLOR", (0, i + 1), (0, i + 1), severity_colors[sev]))
        sev_table.setStyle(TableStyle(sev_style))
        elements.append(sev_table)
        elements.append(Spacer(1, 8 * mm))

    # Test results summary
    tests_passed = summary.get("tests_passed", 0)
    tests_failed = summary.get("tests_failed", 0)
    if tests_passed or tests_failed:
        elements.append(Paragraph("Test Results", heading_style))
        test_data = [
            ["Tests Passed", str(tests_passed)],
            ["Tests Failed", str(tests_failed)],
        ]
        test_table = Table(test_data, colWidths=[120, 80])
        test_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("PADDING", (0, 0), (-1, -1), 6),
        ]))
        elements.append(test_table)
        elements.append(Spacer(1, 8 * mm))

    # Issues table
    issues = scan_data.get("issues", [])
    if issues:
        elements.append(Paragraph(f"Issues ({len(issues)})", heading_style))
        issue_headers = ["#", "Severity", "File", "Title"]
        issue_data = [issue_headers]
        for idx, issue in enumerate(issues[:100], 1):  # cap at 100 for PDF size
            title_text = issue.get("title", "N/A")
            if len(title_text) > 60:
                title_text = title_text[:57] + "..."
            file_path = issue.get("file_path", "N/A")
            if len(file_path) > 30:
                file_path = "..." + file_path[-27:]
            issue_data.append([
                str(idx),
                issue.get("severity", "medium").title(),
                file_path,
                title_text,
            ])

        issue_table = Table(issue_data, colWidths=[30, 70, 150, 220])
        issue_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#374151")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
        ]
        issue_table.setStyle(TableStyle(issue_style))
        elements.append(issue_table)

    doc.build(elements)
    return buffer.getvalue()
