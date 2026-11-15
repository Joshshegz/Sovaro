import io
import csv
import json
import re
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak, HRFlowable
)
from reportlab.pdfgen import canvas
from .ai_service import generate_with_fallback, extract_json_from_llm


# ============================================================================
# 1. DETERMINISTIC SCORECARD CALCULATIONS & METRIC LOGIC
# ============================================================================

STANDARD_METRIC_KEYS = [
    ('followers_total', 'Followers (Total/End)'),
    ('followers_start', 'Followers (Start of Period)'),
    ('followers_growth', 'Net Followers Growth'),
    ('reach', 'Total Reach'),
    ('impressions', 'Total Impressions'),
    ('engagements', 'Total Engagements'),
    ('engagement_rate', 'Engagement Rate (%)'),
    ('link_clicks', 'Outbound Link Clicks'),
    ('conversions', 'Leads / Conversions'),
    ('posts_count', 'Posts Published'),
]


def safe_float(val):
    """Safely converts string or number to float, removing commas, %, and whitespace."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(',', '').replace('%', '')
    if not s or s.lower() in ('n/a', 'none', 'null', '-'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def calculate_change(current, previous):
    """
    Deterministically calculates absolute and percentage change between two numbers.
    Zero-baseline and missing values are handled strictly without division by zero.

    Returns:
        {
            "abs_change": float or None,
            "pct_change": float or None,
            "change_type": "positive" | "negative" | "neutral" | "no_baseline" | "zero_baseline",
            "display_text": str
        }
    """
    curr = safe_float(current)
    prev = safe_float(previous)

    if curr is None:
        return {
            "abs_change": None,
            "pct_change": None,
            "change_type": "no_data",
            "display_text": "No data"
        }

    if prev is None:
        return {
            "abs_change": None,
            "pct_change": None,
            "change_type": "no_baseline",
            "display_text": "N/A (No prior baseline)"
        }

    abs_change = round(curr - prev, 2)

    if prev == 0:
        if curr == 0:
            return {
                "abs_change": 0.0,
                "pct_change": 0.0,
                "change_type": "neutral",
                "display_text": "0.0% (Unchanged at 0)"
            }
        else:
            return {
                "abs_change": abs_change,
                "pct_change": None,
                "change_type": "zero_baseline",
                "display_text": f"+{curr:g} (Baseline was zero)" if abs_change > 0 else f"{curr:g} (Baseline was zero)"
            }

    # Standard percentage calculation
    pct_change = round(((curr - prev) / abs(prev)) * 100, 2)
    change_type = "positive" if pct_change > 0 else ("negative" if pct_change < 0 else "neutral")
    prefix = "+" if pct_change > 0 else ""
    return {
        "abs_change": abs_change,
        "pct_change": pct_change,
        "change_type": change_type,
        "display_text": f"{prefix}{pct_change}%"
    }


def build_scorecard(current_metrics, previous_metrics=None, targets=None):
    """
    Builds a complete, deterministic scorecard for all available metrics.
    Compares current metrics to previous_metrics and targets.
    """
    previous_metrics = previous_metrics or {}
    targets = targets or {}
    scorecard = {}

    # All candidate keys from current + previous + targets
    all_keys = set(current_metrics.keys()) | set(previous_metrics.keys()) | set(targets.keys())

    # Order standard keys first, then custom keys
    standard_dict = dict(STANDARD_METRIC_KEYS)
    ordered_keys = [k for k, _ in STANDARD_METRIC_KEYS if k in all_keys]
    for k in sorted(all_keys):
        if k not in ordered_keys:
            ordered_keys.append(k)

    for key in ordered_keys:
        curr_val = current_metrics.get(key)
        prev_val = previous_metrics.get(key)
        target_val = targets.get(key)

        curr_num = safe_float(curr_val)
        prev_num = safe_float(prev_val)
        target_num = safe_float(target_val)

        label = standard_dict.get(key, key.replace('_', ' ').title())
        comparison = calculate_change(curr_num, prev_num)

        # Target attainment calculation
        target_status = "none"
        target_pct = None
        if curr_num is not None and target_num is not None and target_num > 0:
            target_pct = round((curr_num / target_num) * 100, 1)
            if target_pct >= 100:
                target_status = "achieved"
            elif target_pct >= 80:
                target_status = "on_track"
            else:
                target_status = "lagging"

        scorecard[key] = {
            "key": key,
            "label": label,
            "current": curr_num if curr_num is not None else curr_val,
            "previous": prev_num if prev_num is not None else prev_val,
            "target": target_num if target_num is not None else target_val,
            "abs_change": comparison["abs_change"],
            "pct_change": comparison["pct_change"],
            "change_type": comparison["change_type"],
            "display_change": comparison["display_text"],
            "target_pct": target_pct,
            "target_status": target_status
        }

    return scorecard


# ============================================================================
# 2. CSV IMPORT & VALIDATION ENGINE
# ============================================================================

def parse_and_validate_csv(csv_content):
    """
    Parses and validates CSV text or file stream.
    Supports two formats:
      Format A: Post-Level Analytics CSV
        Columns: date, platform, post_title_or_hook, format, impressions, reach, engagements, likes, comments, shares, clicks, conversions
      Format B: Summary Metrics CSV
        Columns: metric, current_value, previous_value, target

    Returns:
      {
        "format": "post_level" | "summary_metrics",
        "valid_rows_count": int,
        "invalid_rows_count": int,
        "warnings": [str],
        "errors": [str],
        "aggregated_metrics": dict,
        "previous_metrics": dict,
        "targets": dict,
        "post_records": list of dicts,
        "preview_rows": list of dicts
      }
    """
    if isinstance(csv_content, bytes):
        try:
            csv_content = csv_content.decode('utf-8-sig')  # Handles UTF-8 with or without BOM
        except UnicodeDecodeError:
            csv_content = csv_content.decode('latin-1')

    if not csv_content or not csv_content.strip():
        return {
            "is_valid": False,
            "errors": ["Uploaded CSV file is empty."],
            "warnings": [],
            "post_records": [],
            "aggregated_metrics": {},
            "previous_metrics": {},
            "targets": {},
            "preview_rows": []
        }

    # Normalize newlines
    lines = csv_content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    lines = [line.strip() for line in lines if line.strip()]

    if not lines:
        return {
            "is_valid": False,
            "errors": ["Uploaded CSV has no content rows."],
            "warnings": [],
            "post_records": [],
            "aggregated_metrics": {},
            "previous_metrics": {},
            "targets": {},
            "preview_rows": []
        }

    reader = csv.reader(lines)
    try:
        raw_headers = next(reader)
    except StopIteration:
        return {
            "is_valid": False,
            "errors": ["Could not read headers from CSV."],
            "warnings": [],
            "post_records": [],
            "aggregated_metrics": {},
            "previous_metrics": {},
            "targets": {},
            "preview_rows": []
        }

    # Normalize headers
    headers = [re.sub(r'[^a-z0-9_]', '', h.strip().lower().replace(' ', '_').replace('-', '_')) for h in raw_headers]

    # Detect format:
    # Summary format typically has 'metric' and 'current_value'
    is_summary_format = 'metric' in headers and any(h in headers for h in ['current_value', 'value', 'current'])

    if is_summary_format:
        return _parse_summary_csv(reader, headers)
    else:
        return _parse_post_level_csv(reader, headers)


def _parse_summary_csv(reader, headers):
    metric_idx = headers.index('metric')
    curr_idx = headers.index('current_value') if 'current_value' in headers else (headers.index('current') if 'current' in headers else headers.index('value'))
    prev_idx = headers.index('previous_value') if 'previous_value' in headers else (headers.index('previous') if 'previous' in headers else None)
    target_idx = headers.index('target') if 'target' in headers else (headers.index('target_value') if 'target_value' in headers else None)

    aggregated_metrics = {}
    previous_metrics = {}
    targets = {}
    warnings = []
    errors = []
    preview_rows = []
    valid_count = 0
    invalid_count = 0

    for line_num, row in enumerate(reader, start=2):
        if not row or not any(row):
            continue
        if len(row) <= metric_idx:
            errors.append(f"Row {line_num}: Missing metric name.")
            invalid_count += 1
            continue

        raw_metric = row[metric_idx].strip()
        if not raw_metric:
            errors.append(f"Row {line_num}: Empty metric name.")
            invalid_count += 1
            continue

        metric_key = re.sub(r'[^a-z0-9_]', '', raw_metric.lower().replace(' ', '_').replace('-', '_'))

        curr_raw = row[curr_idx].strip() if len(row) > curr_idx else ""
        curr_num = safe_float(curr_raw)

        if curr_raw and curr_num is None:
            warnings.append(f"Row {line_num} ('{raw_metric}'): Value '{curr_raw}' is not numeric. Treated as string.")
            aggregated_metrics[metric_key] = curr_raw
        elif curr_num is not None:
            aggregated_metrics[metric_key] = curr_num

        if prev_idx is not None and len(row) > prev_idx:
            prev_raw = row[prev_idx].strip()
            prev_num = safe_float(prev_raw)
            if prev_num is not None:
                previous_metrics[metric_key] = prev_num

        if target_idx is not None and len(row) > target_idx:
            target_raw = row[target_idx].strip()
            target_num = safe_float(target_raw)
            if target_num is not None:
                targets[metric_key] = target_num

        valid_count += 1
        if len(preview_rows) < 10:
            preview_rows.append({
                "metric": raw_metric,
                "current": curr_raw,
                "previous": row[prev_idx].strip() if prev_idx is not None and len(row) > prev_idx else "-",
                "target": row[target_idx].strip() if target_idx is not None and len(row) > target_idx else "-"
            })

    # Auto-calculate net followers growth if start and end exist
    if 'followers_start' in aggregated_metrics and 'followers_total' in aggregated_metrics and 'followers_growth' not in aggregated_metrics:
        try:
            aggregated_metrics['followers_growth'] = round(aggregated_metrics['followers_total'] - aggregated_metrics['followers_start'], 2)
        except Exception:
            pass

    return {
        "is_valid": len(errors) == 0 and valid_count > 0,
        "format": "summary_metrics",
        "valid_rows_count": valid_count,
        "invalid_rows_count": invalid_count,
        "warnings": warnings,
        "errors": errors,
        "aggregated_metrics": aggregated_metrics,
        "previous_metrics": previous_metrics,
        "targets": targets,
        "post_records": [],
        "preview_rows": preview_rows
    }


def _parse_post_level_csv(reader, headers):
    """
    Parses post-by-post analytics.
    Recognizes columns like:
      - title/hook/caption: 'post_title_or_hook', 'hook', 'title', 'caption', 'post'
      - platform: 'platform', 'channel'
      - format: 'format', 'type', 'content_type'
      - reach: 'reach', 'unique_reach'
      - impressions: 'impressions', 'views'
      - engagements: 'engagements', 'total_engagements'
      - likes: 'likes', 'reactions'
      - comments: 'comments'
      - shares: 'shares', 'reposts', 'retweets'
      - clicks: 'clicks', 'link_clicks', 'outbound_clicks'
      - conversions: 'conversions', 'leads'
      - date: 'date', 'published_at', 'post_date'
    """
    def find_idx(candidates):
        for c in candidates:
            if c in headers:
                return headers.index(c)
        return None

    title_idx = find_idx(['post_title_or_hook', 'title', 'hook', 'caption', 'post', 'name'])
    platform_idx = find_idx(['platform', 'channel', 'network'])
    format_idx = find_idx(['format', 'content_type', 'type'])
    reach_idx = find_idx(['reach', 'unique_reach', 'accounts_reached'])
    imp_idx = find_idx(['impressions', 'views', 'post_impressions'])
    eng_idx = find_idx(['engagements', 'total_engagements', 'interactions'])
    likes_idx = find_idx(['likes', 'reactions'])
    comments_idx = find_idx(['comments'])
    shares_idx = find_idx(['shares', 'reposts', 'retweets'])
    clicks_idx = find_idx(['clicks', 'link_clicks', 'outbound_clicks'])
    conv_idx = find_idx(['conversions', 'leads', 'signups'])
    date_idx = find_idx(['date', 'published_at', 'post_date', 'timestamp'])

    if title_idx is None and imp_idx is None and reach_idx is None:
        return {
            "is_valid": False,
            "errors": [
                "Unrecognized CSV format. Headers must include either summary columns ('metric', 'current_value') "
                "or post-level columns ('post_title_or_hook', 'platform', 'impressions', 'reach', 'engagements'). "
                f"Found headers: {', '.join(headers[:8])}"
            ],
            "warnings": [],
            "post_records": [],
            "aggregated_metrics": {},
            "previous_metrics": {},
            "targets": {},
            "preview_rows": []
        }

    post_records = []
    warnings = []
    errors = []
    preview_rows = []
    valid_count = 0
    invalid_count = 0

    total_reach = 0.0
    total_impressions = 0.0
    total_engagements = 0.0
    total_likes = 0.0
    total_comments = 0.0
    total_shares = 0.0
    total_clicks = 0.0
    total_conversions = 0.0
    platforms_found = set()

    for line_num, row in enumerate(reader, start=2):
        if not row or not any(row):
            continue

        title = row[title_idx].strip() if title_idx is not None and len(row) > title_idx else f"Post #{line_num - 1}"
        platform = row[platform_idx].strip() if platform_idx is not None and len(row) > platform_idx else "General"
        post_format = row[format_idx].strip() if format_idx is not None and len(row) > format_idx else "Post"
        post_date = row[date_idx].strip() if date_idx is not None and len(row) > date_idx else ""

        reach = safe_float(row[reach_idx]) if reach_idx is not None and len(row) > reach_idx else 0.0
        imp = safe_float(row[imp_idx]) if imp_idx is not None and len(row) > imp_idx else 0.0
        eng = safe_float(row[eng_idx]) if eng_idx is not None and len(row) > eng_idx else 0.0
        likes = safe_float(row[likes_idx]) if likes_idx is not None and len(row) > likes_idx else 0.0
        comments = safe_float(row[comments_idx]) if comments_idx is not None and len(row) > comments_idx else 0.0
        shares = safe_float(row[shares_idx]) if shares_idx is not None and len(row) > shares_idx else 0.0
        clicks = safe_float(row[clicks_idx]) if clicks_idx is not None and len(row) > clicks_idx else 0.0
        conv = safe_float(row[conv_idx]) if conv_idx is not None and len(row) > conv_idx else 0.0

        reach = reach or 0.0
        imp = imp or 0.0
        eng = eng or 0.0
        likes = likes or 0.0
        comments = comments or 0.0
        shares = shares or 0.0
        clicks = clicks or 0.0
        conv = conv or 0.0

        # If engagements not explicitly provided, sum component interactions
        if eng == 0.0 and (likes > 0 or comments > 0 or shares > 0):
            eng = likes + comments + shares

        # Post-level engagement rate calculation
        post_eng_rate = round((eng / imp * 100), 2) if imp > 0 else (round((eng / reach * 100), 2) if reach > 0 else 0.0)

        record = {
            "title": title,
            "platform": platform,
            "format": post_format,
            "date": post_date,
            "reach": reach,
            "impressions": imp,
            "engagements": eng,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "clicks": clicks,
            "conversions": conv,
            "engagement_rate": post_eng_rate
        }

        post_records.append(record)
        platforms_found.add(platform)

        total_reach += reach
        total_impressions += imp
        total_engagements += eng
        total_likes += likes
        total_comments += comments
        total_shares += shares
        total_clicks += clicks
        total_conversions += conv

        valid_count += 1
        if len(preview_rows) < 10:
            preview_rows.append(record)

    # Compute overall aggregates
    posts_count = len(post_records)
    avg_eng_rate = 0.0
    if total_impressions > 0:
        avg_eng_rate = round((total_engagements / total_impressions) * 100, 2)
    elif total_reach > 0:
        avg_eng_rate = round((total_engagements / total_reach) * 100, 2)

    aggregated_metrics = {
        "posts_count": posts_count,
        "reach": round(total_reach, 2),
        "impressions": round(total_impressions, 2),
        "engagements": round(total_engagements, 2),
        "engagement_rate": avg_eng_rate,
        "link_clicks": round(total_clicks, 2),
        "conversions": round(total_conversions, 2),
    }

    return {
        "is_valid": valid_count > 0,
        "format": "post_level",
        "valid_rows_count": valid_count,
        "invalid_rows_count": invalid_count,
        "warnings": warnings,
        "errors": errors,
        "aggregated_metrics": aggregated_metrics,
        "previous_metrics": {},
        "targets": {},
        "post_records": post_records,
        "platforms_covered": sorted(list(platforms_found)),
        "preview_rows": preview_rows
    }


def analyze_content_performance(post_records):
    """
    Identifies top-performing and underperforming content pieces deterministically
    based on engagement, reach, and engagement rate.
    """
    if not post_records:
        return {
            "top_posts": [],
            "underperforming_posts": [],
            "format_breakdown": {},
            "summary": "No post-level data available for detailed content breakdown."
        }

    # Sort by engagements, then impressions
    sorted_posts = sorted(post_records, key=lambda p: (p.get('engagements', 0), p.get('impressions', 0)), reverse=True)
    top_posts = sorted_posts[:3]
    underperforming_posts = sorted_posts[-3:] if len(sorted_posts) >= 6 else []

    # Format breakdown
    format_stats = {}
    for p in post_records:
        fmt = p.get('format', 'Unspecified') or 'Unspecified'
        if fmt not in format_stats:
            format_stats[fmt] = {'count': 0, 'impressions': 0.0, 'engagements': 0.0}
        format_stats[fmt]['count'] += 1
        format_stats[fmt]['impressions'] += p.get('impressions', 0.0)
        format_stats[fmt]['engagements'] += p.get('engagements', 0.0)

    # Calculate average engagement rate per format
    format_breakdown = {}
    for fmt, data in format_stats.items():
        avg_rate = round((data['engagements'] / data['impressions'] * 100), 2) if data['impressions'] > 0 else 0.0
        format_breakdown[fmt] = {
            "count": data['count'],
            "total_impressions": data['impressions'],
            "total_engagements": data['engagements'],
            "avg_engagement_rate": avg_rate
        }

    return {
        "top_posts": top_posts,
        "underperforming_posts": underperforming_posts,
        "format_breakdown": format_breakdown,
        "summary": f"Analyzed {len(post_records)} post records across {len(format_breakdown)} content formats."
    }


# ============================================================================
# 3. AI REPORT SYNTHESIS PIPELINE (GEMINI)
# ============================================================================

def generate_report_narratives(brand, month_year, scorecard, content_performance, context=None):
    """
    Synthesizes the qualitative sections of the executive report using Gemini AI:
      1. Executive summary (2-3 paragraphs with high-impact conclusions)
      2. Strategic insights (distinguishing verified observations, plausible hypotheses, test recommendations)
      3. Objective assessment (evaluating against brand goals and targets)
      4. Recommendations for next month (prioritized actions with rationale and expected outcome)

    All arithmetic is pre-calculated and injected as fixed ground truth.
    Prompt instructs AI never to recalculate, invent figures, or contradict scorecard numbers.
    """
    brand_name = brand.name
    brand_niche = getattr(brand, 'niche', '') or 'General'
    target_audience = getattr(brand, 'target_audience', '') or 'Target Customers'
    tone = getattr(brand, 'tone_of_voice', '') or 'Professional & Authoritative'
    context = context or {}
    platforms = context.get('platforms_covered', [])
    platforms_str = ", ".join(platforms) if platforms else "All Active Channels"

    # Format scorecard summary for LLM context
    scorecard_lines = []
    for key, data in scorecard.items():
        curr = data['current']
        prev = data.get('previous')
        chg = data.get('display_change', 'N/A')
        tgt = data.get('target')
        line = f"- {data['label']}: Current = {curr}"
        if prev is not None:
            line += f", Previous = {prev} (Change: {chg})"
        if tgt is not None:
            status = data.get('target_status', 'none')
            line += f", Target = {tgt} ({status.upper()})"
        scorecard_lines.append(line)
    scorecard_text = "\n".join(scorecard_lines)

    # Format content performance summary
    top_posts_lines = []
    for idx, p in enumerate(content_performance.get('top_posts', []), 1):
        top_posts_lines.append(
            f"  {idx}. '{p.get('title')}' [{p.get('platform')}, {p.get('format')}]: "
            f"{p.get('impressions', 0):g} views, {p.get('engagements', 0):g} engagements, {p.get('engagement_rate', 0)}% eng rate"
        )
    top_posts_text = "\n".join(top_posts_lines) if top_posts_lines else "  No post-level breakdown provided."

    format_lines = []
    for fmt, f_data in content_performance.get('format_breakdown', {}).items():
        format_lines.append(f"  - {fmt}: {f_data['count']} posts, {f_data['avg_engagement_rate']}% avg eng rate")
    format_text = "\n".join(format_lines) if format_lines else "  No format breakdown available."

    prompt = f"""
You are an Enterprise Principal Social Media Strategist and Marketing Analytics Lead.
You are generating a client-ready, data-grounded Monthly Performance Report.

BRAND CONTEXT:
- Brand Name: {brand_name}
- Industry / Niche: {brand_niche}
- Target Audience: {target_audience}
- Tone of Voice: {tone}
- Reporting Period: {month_year}
- Channels Evaluated: {platforms_str}

VERIFIED PERFORMANCE SCORECARD (GROUND TRUTH ARITHMETIC — DO NOT RECALCULATE):
{scorecard_text}

CONTENT PERFORMANCE & TOP POSTS:
{top_posts_text}

FORMAT LEVEL BENCHMARKS:
{format_text}

CRITICAL RULES FOR ANALYSIS:
1. STRICT ARITHMETIC GROUNDING: Reference ONLY the verified numbers given above. Never contradict the scorecard or invent hypothetical metrics.
2. EMPIRICAL RIGOR: In Strategic Insights, clearly classify findings into:
   - "verified_observation": Directly supported by the data points.
   - "plausible_hypothesis": Likely strategic explanation of why it occurred.
   - "test_recommendation": How to validate or test this further.
3. OBJECTIVE ASSESSMENT: Classify each key goal as "achieved", "partially_achieved", "missed", or "insufficient_data" with clear rationale.
4. ACTIONABLE RECOMMENDATIONS: Provide 3-4 prioritized next-month directives with clear rationale and expected impact.
5. NO VAGUE BUZZWORDS: Avoid "synergy", "supercharge", "game-changing". Use direct, executive language.

Return a valid JSON object matching this exact schema:
{{
  "executive_summary": "Comprehensive 2-3 paragraph executive summary evaluating total performance, significant gains or losses, and high-level trajectory against objectives.",
  "key_insights": [
    "Short high-impact bullet 1 summarizing primary win with numbers",
    "Short high-impact bullet 2 summarizing conversion or engagement reality",
    "Short high-impact bullet 3 highlighting area for improvement"
  ],
  "strategic_insights": [
    {{
      "theme": "Theme title (e.g. Video Hook Retention, LinkedIn Document Authority)",
      "observation": "Direct factual observation grounded strictly in the provided data",
      "hypothesis": "Plausible strategic rationale explaining audience behavior",
      "test_next_month": "Specific test or experiment to validate"
    }}
  ],
  "objective_assessment": [
    {{
      "objective": "Objective or KPI evaluated",
      "status": "achieved" or "partially_achieved" or "missed" or "insufficient_data",
      "evaluation": "Data-backed explanation of progress against goal"
    }}
  ],
  "next_month_recommendations": [
    {{
      "priority": "High" or "Medium",
      "action": "Specific tactical action for next month",
      "rationale": "Why this action is warranted by current performance",
      "expected_outcome": "Measurable business or engagement outcome anticipated"
    }}
  ],
  "next_month_strategy": {{
    "double_down": "Direct action to repeat and scale what worked best",
    "test": "Specific hypothesis experiment to run next period",
    "stop": "Effort, format, or topic to discontinue or revise"
  }}
}}

Return ONLY valid JSON.
"""

    response = generate_with_fallback(prompt)
    narratives = extract_json_from_llm(response.text)

    # Validate output schema
    if not isinstance(narratives, dict):
        raise ValueError("AI response did not return a valid dictionary.")

    return {
        "executive_summary": narratives.get("executive_summary", "Monthly performance report completed."),
        "key_insights": narratives.get("key_insights", []),
        "strategic_insights": narratives.get("strategic_insights", []),
        "objective_assessment": narratives.get("objective_assessment", []),
        "next_month_recommendations": narratives.get("next_month_recommendations", []),
        "next_month_strategy": narratives.get("next_month_strategy", {
            "double_down": "Scale top-performing content formats.",
            "test": "Experiment with new hook structures.",
            "stop": "Discontinue low-engagement formats."
        })
    }


# ============================================================================
# 4. REPORTLAB PROFESSIONAL PDF GENERATOR
# ============================================================================

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y' and header/footer.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer
        footer_text = f"Sovaro Intelligence Suite  |  Confidential Monthly Report  |  Page {self._pageNumber} of {total_pages}"
        self.drawRightString(letter[0] - 36, 25, footer_text)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(36, 40, letter[0] - 36, 40)

        # Header (Pages > 1)
        if self._pageNumber > 1:
            self.drawString(36, letter[1] - 30, "Sovaro Executive Monthly Report")
            self.line(36, letter[1] - 36, letter[0] - 36, letter[1] - 36)

        self.restoreState()


def build_report_pdf(report):
    """
    Builds a professional, print-ready, high-aesthetic executive PDF report
    using ReportLab. Returns PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=46,
        bottomMargin=50
    )

    styles = getSampleStyleSheet()

    # Custom Color Palette
    c_navy = colors.HexColor("#0f172a")
    c_indigo = colors.HexColor("#4f46e5")
    c_indigo_light = colors.HexColor("#eef2ff")
    c_slate = colors.HexColor("#334155")
    c_muted = colors.HexColor("#64748b")
    c_border = colors.HexColor("#cbd5e1")
    c_emerald = colors.HexColor("#10b981")
    c_emerald_bg = colors.HexColor("#ecfdf5")
    c_amber = colors.HexColor("#f59e0b")
    c_rose = colors.HexColor("#ef4444")

    # Custom Typography Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=c_navy,
        spaceAfter=4
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=c_muted,
        spaceAfter=14
    )
    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=c_navy,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=c_slate,
        spaceAfter=6
    )
    badge_style = ParagraphStyle(
        'Badge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=c_indigo
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=c_slate
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=c_navy
    )
    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9.5,
        leading=14,
        textColor=c_navy
    )

    story = []

    # ── 1. HEADER & META BANNER ──────────────────────────────────────────
    brand_name = report.brand.name if report.brand else "Brand Report"
    story.append(Paragraph(f"Executive Monthly Performance Report", title_style))
    story.append(Paragraph(f"<b>{brand_name}</b> &nbsp;|&nbsp; Period: <b>{report.month_year}</b>", subtitle_style))

    # Meta card table (Platforms, Generated Date, Provenance)
    platforms = ", ".join(report.platforms_covered) if report.platforms_covered else "Multi-Platform"
    gen_date = report.created_at.strftime("%B %d, %Y") if report.created_at else datetime.now().strftime("%B %d, %Y")
    provenance_label = "CSV Import (Post-Level)" if report.data_provenance == "csv_import" else "Direct Analytics Entry"

    meta_data = [
        [
            Paragraph("<b>Target Brand:</b>", table_cell),
            Paragraph(brand_name, table_cell_bold),
            Paragraph("<b>Reporting Period:</b>", table_cell),
            Paragraph(report.month_year, table_cell_bold),
        ],
        [
            Paragraph("<b>Channels Covered:</b>", table_cell),
            Paragraph(platforms, table_cell),
            Paragraph("<b>Report Generated:</b>", table_cell),
            Paragraph(gen_date, table_cell),
        ],
        [
            Paragraph("<b>Data Provenance:</b>", table_cell),
            Paragraph(provenance_label, table_cell),
            Paragraph("<b>Status:</b>", table_cell),
            Paragraph("Verified Client Deliverable", table_cell_bold),
        ]
    ]
    t_meta = Table(meta_data, colWidths=[1.3*inch, 2.2*inch, 1.4*inch, 2.1*inch])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_indigo_light),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e0e7ff")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 14))

    # ── 2. KEY WINS BAR (INVERTED PYRAMID — CEO-LEVEL SCAN) ──────────────
    key_insights = report.key_insights or []
    if key_insights:
        wins_style = ParagraphStyle(
            'WinsBullet',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=15,
            textColor=c_slate,
            leftIndent=10,
            spaceAfter=3
        )
        wins_title = ParagraphStyle(
            'WinsTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            textColor=c_emerald,
            spaceAfter=6
        )
        wins_data = [[Paragraph("⚡ KEY WINS THIS PERIOD", wins_title)]]
        for insight in key_insights:
            wins_data.append([Paragraph(f"✓  {insight}", wins_style)])

        t_wins = Table(wins_data, colWidths=[7.0*inch])
        t_wins.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), c_emerald_bg),
            ('BOX', (0,0), (-1,-1), 0.8, c_emerald),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t_wins)
        story.append(Spacer(1, 12))

    # ── 3. EXECUTIVE SUMMARY ─────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", h2_style))
    exec_summary = report.executive_summary or "Monthly performance analysis concluded successfully."
    # Render paragraph blocks
    for p_block in exec_summary.split("\n\n"):
        if p_block.strip():
            story.append(Paragraph(p_block.strip(), body_style))
    story.append(Spacer(1, 8))


    # ── 3. PERFORMANCE SCORECARD (DETERMINISTIC MATH) ─────────────────────
    story.append(Paragraph("2. Performance Scorecard & Period Comparison", h2_style))
    scorecard = report.scorecard_data or {}

    scorecard_rows = [
        [
            Paragraph("<b>Metric</b>", table_cell_bold),
            Paragraph("<b>Current</b>", table_cell_bold),
            Paragraph("<b>Previous</b>", table_cell_bold),
            Paragraph("<b>Change</b>", table_cell_bold),
            Paragraph("<b>Target</b>", table_cell_bold)
        ]
    ]

    for key, item in scorecard.items():
        curr_str = f"{item.get('current'):,g}" if isinstance(item.get('current'), (int, float)) else str(item.get('current') or '-')
        prev_str = f"{item.get('previous'):,g}" if isinstance(item.get('previous'), (int, float)) else (str(item.get('previous')) if item.get('previous') is not None else "-")
        chg_str = item.get('display_change', '-')
        tgt_str = f"{item.get('target'):,g}" if isinstance(item.get('target'), (int, float)) else (str(item.get('target')) if item.get('target') is not None else "-")

        chg_color = c_navy
        if item.get('change_type') == 'positive':
            chg_color = c_emerald
        elif item.get('change_type') == 'negative':
            chg_color = c_rose

        chg_style = ParagraphStyle(
            f'Chg_{key}',
            parent=table_cell,
            textColor=chg_color,
            fontName='Helvetica-Bold' if item.get('change_type') in ('positive', 'negative') else 'Helvetica'
        )

        scorecard_rows.append([
            Paragraph(item.get('label', key), table_cell_bold),
            Paragraph(curr_str, table_cell),
            Paragraph(prev_str, table_cell),
            Paragraph(chg_str, chg_style),
            Paragraph(tgt_str, table_cell)
        ])

    if len(scorecard_rows) == 1:
        scorecard_rows.append([Paragraph("No metric entries provided.", table_cell), Paragraph("-", table_cell), Paragraph("-", table_cell), Paragraph("-", table_cell), Paragraph("-", table_cell)])

    t_scorecard = Table(scorecard_rows, colWidths=[2.2*inch, 1.2*inch, 1.2*inch, 1.4*inch, 1.0*inch])
    t_scorecard.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
        ('BOX', (0,0), (-1,-1), 1, c_border),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_scorecard)
    story.append(Spacer(1, 14))

    # ── 4. CONTENT PERFORMANCE (POST-LEVEL HIGHLIGHTS) ───────────────────
    content_perf = report.content_performance or {}
    top_posts = content_perf.get('top_posts', [])
    if top_posts:
        story.append(Paragraph("3. Top Performing Content Pieces", h2_style))
        post_rows = [
            [
                Paragraph("<b>Post / Hook</b>", table_cell_bold),
                Paragraph("<b>Platform</b>", table_cell_bold),
                Paragraph("<b>Format</b>", table_cell_bold),
                Paragraph("<b>Impressions</b>", table_cell_bold),
                Paragraph("<b>Engagements</b>", table_cell_bold),
                Paragraph("<b>Eng Rate</b>", table_cell_bold)
            ]
        ]
        for p in top_posts:
            post_rows.append([
                Paragraph(p.get('title', 'Post')[:55] + ('...' if len(p.get('title', '')) > 55 else ''), table_cell),
                Paragraph(p.get('platform', '-'), table_cell),
                Paragraph(p.get('format', '-'), table_cell),
                Paragraph(f"{p.get('impressions', 0):,g}", table_cell),
                Paragraph(f"{p.get('engagements', 0):,g}", table_cell),
                Paragraph(f"{p.get('engagement_rate', 0)}%", table_cell_bold)
            ])
        t_posts = Table(post_rows, colWidths=[2.4*inch, 0.9*inch, 1.1*inch, 1.0*inch, 0.9*inch, 0.7*inch])
        t_posts.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f8fafc")),
            ('BOX', (0,0), (-1,-1), 1, c_border),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t_posts)
        story.append(Spacer(1, 10))

    # Underperforming posts (bottom content)
    under_posts = content_perf.get('underperforming_posts', [])
    if under_posts:
        story.append(Paragraph("3b. Underperforming Content (Needs Review)", ParagraphStyle(
            'SubH2', parent=styles['Heading3'], fontName='Helvetica-Bold',
            fontSize=11, leading=14, textColor=c_rose, spaceBefore=4, spaceAfter=6
        )))
        under_rows = [
            [
                Paragraph("<b>Post / Hook</b>", table_cell_bold),
                Paragraph("<b>Platform</b>", table_cell_bold),
                Paragraph("<b>Format</b>", table_cell_bold),
                Paragraph("<b>Impressions</b>", table_cell_bold),
                Paragraph("<b>Eng Rate</b>", table_cell_bold),
            ]
        ]
        for p in under_posts:
            under_rows.append([
                Paragraph(p.get('title', 'Post')[:50] + ('...' if len(p.get('title', '')) > 50 else ''), table_cell),
                Paragraph(p.get('platform', '-'), table_cell),
                Paragraph(p.get('format', '-'), table_cell),
                Paragraph(f"{p.get('impressions', 0):,g}", table_cell),
                Paragraph(f"{p.get('engagement_rate', 0)}%", ParagraphStyle('EngLow', parent=table_cell, textColor=c_rose)),
            ])
        t_under = Table(under_rows, colWidths=[2.9*inch, 0.9*inch, 1.1*inch, 1.2*inch, 0.9*inch])
        t_under.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#fff1f2")),
            ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#fca5a5")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#fee2e2")),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(t_under)
        story.append(Spacer(1, 14))



    # ── 5. STRATEGIC INSIGHTS (OBSERVATION / HYPOTHESIS / TEST) ───────────
    strategic_insights = report.strategic_insights or []
    if strategic_insights:
        story.append(Paragraph("4. Strategic Insights & Analytical Observations", h2_style))
        for ins in strategic_insights:
            if isinstance(ins, dict):
                theme = ins.get('theme', 'Strategic Finding')
                obs = ins.get('observation', '')
                hyp = ins.get('hypothesis', '')
                tst = ins.get('test_next_month', '')

                insight_box_data = [
                    [Paragraph(f"<b>Insight: {theme}</b>", table_cell_bold)],
                    [Paragraph(f"<b>Verified Observation:</b> {obs}", table_cell)],
                    [Paragraph(f"<b>Strategic Hypothesis:</b> {hyp}", callout_style)],
                    [Paragraph(f"<b>Validation Experiment:</b> {tst}", table_cell)]
                ]
                t_box = Table(insight_box_data, colWidths=[7.0*inch])
                t_box.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
                    ('BOX', (0,0), (-1,-1), 0.5, c_border),
                    ('LINEBELOW', (0,0), (-1,0), 0.5, colors.HexColor("#e2e8f0")),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(t_box)
                story.append(Spacer(1, 6))
        story.append(Spacer(1, 8))

    # ── 6. KPI & OBJECTIVE ASSESSMENT ────────────────────────────────────
    objectives = report.objective_assessment or []
    if objectives:
        story.append(Paragraph("5. KPI & Objective Attainment Assessment", h2_style))
        obj_rows = [
            [
                Paragraph("<b>Strategic Objective</b>", table_cell_bold),
                Paragraph("<b>Attainment Status</b>", table_cell_bold),
                Paragraph("<b>Data-Backed Evaluation</b>", table_cell_bold)
            ]
        ]
        for obj in objectives:
            if isinstance(obj, dict):
                st = obj.get('status', 'partially_achieved').replace('_', ' ').title()
                st_color = c_emerald if 'Achieved' in st and 'Partially' not in st else (c_rose if 'Missed' in st else c_amber)
                status_style = ParagraphStyle('ObjSt', parent=table_cell_bold, textColor=st_color)

                obj_rows.append([
                    Paragraph(obj.get('objective', 'Objective'), table_cell_bold),
                    Paragraph(st, status_style),
                    Paragraph(obj.get('evaluation', '-'), table_cell)
                ])
        t_obj = Table(obj_rows, colWidths=[2.0*inch, 1.4*inch, 3.6*inch])
        t_obj.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f1f5f9")),
            ('BOX', (0,0), (-1,-1), 1, c_border),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_obj)
        story.append(Spacer(1, 14))

    # ── 7. RECOMMENDATIONS FOR NEXT MONTH ────────────────────────────────
    recommendations = report.next_month_recommendations or []
    strategy_directives = report.next_month_strategy or {}

    story.append(Paragraph("6. Prioritized Action Plan for Next Month", h2_style))

    if recommendations:
        for rec in recommendations:
            if isinstance(rec, dict):
                pri = rec.get('priority', 'High')
                act = rec.get('action', '')
                rat = rec.get('rationale', '')
                out = rec.get('expected_outcome', '')

                rec_box = [
                    [Paragraph(f"<b>[{pri} Priority Action]</b> {act}", table_cell_bold)],
                    [Paragraph(f"<b>Strategic Rationale:</b> {rat}", table_cell)],
                    [Paragraph(f"<b>Expected Business Outcome:</b> {out}", callout_style)]
                ]
                t_rec = Table(rec_box, colWidths=[7.0*inch])
                t_rec.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fdfefe")),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#cbd5e1")),
                    ('TOPPADDING', (0,0), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(t_rec)
                story.append(Spacer(1, 5))

    # Legacy strategy directives fallback if next_month_recommendations is empty
    elif strategy_directives:
        dir_rows = [
            [Paragraph("<b>Double Down On</b>", table_cell_bold), Paragraph(str(strategy_directives.get('double_down', '-')), table_cell)],
            [Paragraph("<b>Test Experiment</b>", table_cell_bold), Paragraph(str(strategy_directives.get('test', '-')), table_cell)],
            [Paragraph("<b>Discontinue / Stop</b>", table_cell_bold), Paragraph(str(strategy_directives.get('stop', '-')), table_cell)]
        ]
        t_dir = Table(dir_rows, colWidths=[1.8*inch, 5.2*inch])
        t_dir.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f8fafc")),
            ('BOX', (0,0), (-1,-1), 1, c_border),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#e2e8f0")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(t_dir)

    # Build PDF with two-pass canvas
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
