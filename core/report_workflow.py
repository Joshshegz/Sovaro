"""Small, reviewable monthly report workflow. No inferred causes or invented benchmarks."""

import calendar
import io
from html import escape
from urllib.parse import urlsplit

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .forms import REPORT_METRICS
from .reporting_service import analyze_content_performance, build_scorecard, parse_and_validate_csv


def prepare_report(cleaned):
    """Turn validated form data into a report draft or raise ValueError for bad CSV."""
    month = cleaned["month"]
    month_year = month.strftime("%B %Y")
    start_date = month.replace(day=1)
    end_date = month.replace(day=calendar.monthrange(month.year, month.month)[1])
    current = {key: float(cleaned[f"current_{key}"]) for key, _ in REPORT_METRICS if cleaned.get(f"current_{key}") is not None}
    previous = {key: float(cleaned[f"previous_{key}"]) for key, _ in REPORT_METRICS if cleaned.get(f"previous_{key}") is not None}
    records = []
    provenance = "guided_entry"
    upload = cleaned.get("csv_file")
    if upload:
        try:
            parsed = parse_and_validate_csv(upload.read().decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise ValueError("The CSV must use UTF-8 text.") from exc
        if not parsed.get("is_valid"):
            raise ValueError(" ".join(parsed.get("errors") or ["The CSV has no usable rows."]))
        records = parsed.get("post_records", [])
        for key, value in parsed.get("aggregated_metrics", {}).items():
            if key not in current and value is not None:
                current[key] = value
        for key, value in parsed.get("previous_metrics", {}).items():
            if key not in previous and value is not None:
                previous[key] = value
        provenance = "guided_csv"
    if not current:
        raise ValueError("The CSV had no usable monthly totals. Enter at least one result manually.")
    for line in cleaned.get("top_posts", "").splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if not parts[0]:
            continue
        def number(index):
            try:
                return max(0, float(parts[index].replace(",", "")))
            except (IndexError, ValueError):
                return 0.0
        impressions, engagements = number(2), number(3)
        supplied_url = parts[4] if len(parts) > 4 else ""
        parsed_url = urlsplit(supplied_url)
        safe_url = supplied_url if parsed_url.scheme in ("http", "https") and parsed_url.netloc else ""
        records.append({"title": parts[0], "format": parts[1] if len(parts) > 1 else "Post", "platform": cleaned["platform"], "impressions": impressions, "engagements": engagements, "engagement_rate": round(engagements / impressions * 100, 2) if impressions else 0, "url": safe_url})
    scorecard = build_scorecard(current, previous)
    strongest = next((item for item in scorecard.values() if item["current"] is not None), None)
    if strongest:
        lead = f"{strongest['label']} was {strongest['current']:g} this month."
        comparison = "This is the first recorded month, so these results establish a baseline." if not previous else f"Compared with last month: {strongest['display_change']}."
    else:
        lead, comparison = "Results were entered for this month.", "Review the numbers before sharing."
    performance = analyze_content_performance(records)
    if records:
        performance["top_posts"] = performance["top_posts"][:5]
    top_titles = [str(post.get("title", "Post")) for post in performance.get("top_posts", [])]
    learning = "\n".join(f"Observation: {title} was among the top posts. Hypothesis to check: what topic or format helped? Repeat one element next month." for title in top_titles)
    if not learning:
        learning = "Observation: No post-level results were supplied. Add a post example to assess what worked."
    learning += "\nWhat did not work: Add a verified example or say there is not enough data yet."
    return {
        "month_year": month_year, "start_date": start_date, "end_date": end_date,
        "platforms_covered": [p.strip() for p in cleaned["platform"].split(",") if p.strip()],
        "raw_metrics": current, "previous_period_metrics": previous,
        "scorecard_data": scorecard, "post_records": records,
        "content_performance": performance, "data_provenance": provenance,
        "executive_summary": f"{lead} {comparison} Review the post results and agree on the next test.",
        "what_worked": learning,
        "competitor_snapshot": cleaned.get("competitor_snapshot", "").strip(),
        "next_month_plan": "Choose one theme to repeat, one format or message to test, and a result to check at month end.",
    }


def build_guided_pdf(report):
    """Render the six reviewed sections for reports created in the browser."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=45, rightMargin=45, topMargin=48, bottomMargin=48)
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("ReportHeading", parent=styles["Heading2"], textColor=colors.HexColor("#172033"), spaceBefore=16, spaceAfter=8)
    body = styles["BodyText"]
    story = [Paragraph("Monthly social media report", styles["Title"]), Paragraph(f"{escape(report.brand.name)} | {escape(report.month_year)} | {escape(', '.join(report.platforms_covered))}", body), Spacer(1, 12)]
    if report.status == "draft":
        story += [Paragraph("DRAFT - review before sharing", styles["Heading3"]), Spacer(1, 8)]

    def section(title, value):
        story.append(Paragraph(title, heading))
        for line in (value or "No information added for this section.").splitlines():
            story.append(Paragraph(escape(line) if line else " ", body))

    section("1. Summary", report.executive_summary)
    story.append(Paragraph("2. Key numbers", heading))
    rows = [["Metric", "This month", "Last month", "Change"]]
    for item in (report.scorecard_data or {}).values():
        current = item.get("current")
        previous = item.get("previous")
        rows.append([str(item.get("label", "")), "-" if current is None else str(current), "-" if previous is None else str(previous), str(item.get("display_change", "-"))])
    if len(rows) == 1:
        rows.append(["No results entered", "-", "-", "-"])
    table = Table([[Paragraph(escape(cell), body) for cell in row] for row in rows], colWidths=[2.2 * inch, 1.0 * inch, 1.0 * inch, 2.0 * inch], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")), ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(table)
    story.append(Paragraph("3. Top posts", heading))
    posts = (report.content_performance or {}).get("top_posts", [])
    if posts:
        for post in posts:
            story.append(Paragraph(f"<b>{escape(str(post.get('title', 'Post')))}</b> - {escape(str(post.get('format', 'Post')))}; {post.get('impressions', 0):g} impressions; {post.get('engagements', 0):g} engagements", body))
            if post.get("url"):
                story.append(Paragraph(escape(post["url"]), body))
    else:
        story.append(Paragraph("No post results supplied.", body))
    section("4. What worked and what didn't", report.what_worked)
    section("5. Competitor snapshot", report.competitor_snapshot or "No competitor observations supplied this month.")
    section("6. Next month's plan", report.next_month_plan)
    doc.build(story)
    return buffer.getvalue()
