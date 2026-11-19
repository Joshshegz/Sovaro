"""Build a short, executable trial plan from a strategy and optional public research."""

from .strategy_quality import build_first_week_plan


def build_two_week_plan(brand, data, research):
    capacity = max(1, min(int((data.get("strategy_foundation") or {}).get("weekly_posts") or brand.weekly_posts_capacity), brand.weekly_posts_capacity))
    selected = {str(item.get("platform") or "").lower() for item in data.get("posting_schedule") or []}
    grounded = research.get("source_status") == "grounded"
    researched_ideas = [
        item for item in research.get("ideas") or []
        if item.get("source_url") and str(item.get("platform") or "").lower() in selected
    ] if grounded else []
    original_ideas = [item for item in data.get("content_ideas") or [] if str(item.get("platform") or "").lower() in selected]
    ideas = researched_ideas + original_ideas
    if not ideas:
        ideas = list(data.get("content_ideas") or [])
    weeks = []
    for week in (1, 2):
        start = (week - 1) * capacity
        chunk = ideas[start:start + capacity]
        week_data = {**data, "content_ideas": chunk}
        posts = build_first_week_plan(brand, week_data)
        for index, post in enumerate(posts, 1):
            idea = chunk[index - 1] if index <= len(chunk) else {}
            post["key"] = f"week-{week}-{index}"
            post["week"] = week
            post["source_url"] = idea.get("source_url") or ""
            post["source_brand"] = idea.get("source_brand") or ""
            post["visible_engagement"] = idea.get("visible_engagement") or ""
            post["evidence_status"] = "Public source linked; performance unverified" if post["source_url"] else "Working hypothesis"
        weeks.extend(posts)
    return weeks
