import re


UNSUPPORTED_CLAIM_PATTERNS = (
    r"\bguaranteed\b", r"\b100%\b", r"\bno[- ]risk\b", r"\bonly \d+ spots\b",
    r"\bdermatologist approved\b", r"\bproven to\b",
)


def _number(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def build_first_week_plan(brand, data):
    foundation = data.get("strategy_foundation") or {}
    capacity = max(1, min(int(foundation.get("weekly_posts") or brand.weekly_posts_capacity or 3), brand.weekly_posts_capacity))
    ideas = list(data.get("content_ideas") or [])
    platforms = [item.get("platform") for item in data.get("platform_playbook", []) if item.get("platform")]
    platforms = platforms or list(foundation.get("platforms") or []) or ["Instagram"]
    schedule = []
    for slot in data.get("posting_schedule") or []:
        platform = slot.get("platform")
        if platform:
            schedule.extend([platform] * _number(slot.get("frequency")))
    if len(schedule) != capacity:
        schedule = [platforms[index % len(platforms)] for index in range(capacity)]
    days = ["Monday", "Wednesday", "Friday", "Tuesday", "Thursday", "Saturday", "Sunday"]
    default_formats = list(brand.content_formats or []) or ["Phone video", "Carousel", "Photo with caption"]
    plan = []
    used_ideas = set()
    for index in range(capacity):
        match = next((i for i, item in enumerate(ideas) if i not in used_ideas and str(item.get("platform") or "").lower() == str(schedule[index]).lower()), None)
        if match is None:
            match = next((i for i in range(len(ideas)) if i not in used_ideas), None)
        idea = ideas[match] if match is not None else {}
        if match is not None:
            used_ideas.add(match)
        hook = idea.get("hook") or f"A useful answer to a question {brand.target_audience} often asks"
        concept = idea.get("concept") or "Answer one confirmed customer question using a real example from the business."
        plan.append({
            "key": f"week-1-{index + 1}",
            "day": days[index],
            "platform": schedule[index],
            "format": idea.get("format") or default_formats[index % len(default_formats)],
            "pillar": idea.get("pillar") or "Customer questions",
            "hook": hook,
            "message": concept,
            "cta": _first_cta(data, brand),
            "asset": _asset_for(idea.get("format") or default_formats[index % len(default_formats)]),
            "owner": "Brand owner",
            "status": "draft",
            "evidence_status": idea.get("evidence_status") or "Working hypothesis",
            "reason": idea.get("reason") or "Uses one of the limited weekly slots to answer an audience need and create a measurable response.",
        })
    return plan


def _first_cta(data, brand):
    for item in data.get("cta_strategy") or []:
        examples = item.get("cta_examples") or []
        if examples:
            return examples[0]
    return f"Visit {brand.conversion_url}." if brand.conversion_url else "Send a message to ask about the offer."


def _asset_for(format_name):
    name = str(format_name or "").lower()
    if "video" in name or "reel" in name or "tiktok" in name:
        return "Record a vertical phone video with a spoken hook and on-screen title."
    if "carousel" in name:
        return "Create a cover and 4-6 simple slides, with one idea per slide."
    return "Prepare one clear visual and a caption built around the approved hook."


def validate_strategy(brand, data):
    errors = []
    warnings = []
    passed = []
    foundation = data.get("strategy_foundation") or {}

    owner_goal = (brand.primary_goal or "").strip()
    if owner_goal:
        foundation["owner_stated_goal"] = owner_goal
        passed.append("The brand owner's stated goal is recorded.")
        target_match = re.search(r"\b(?:sell|generate|secure|book|reach|get|gain|achieve|increase)\b[^.]{0,45}?\b(\d+(?:[,.]\d+)?)", owner_goal, re.IGNORECASE)
        owner_numbers = [target_match.group(1)] if target_match else re.findall(r"\d+(?:[,.]\d+)?", owner_goal)
        drafted_goal = str(foundation.get("goal") or "")
        if owner_numbers and drafted_goal and owner_numbers[0] not in re.findall(r"\d+(?:[,.]\d+)?", drafted_goal):
            errors.append("The strategy goal changes the owner's stated numerical target.")
    else:
        errors.append("The brand owner must state a business goal.")

    summary = str(data.get("executive_summary") or "").strip()
    if len(summary) < 35 or brand.name.lower() not in summary.lower():
        errors.append("The executive summary must introduce the brand and explain the direction.")

    if not data.get("content_pillars"):
        errors.append("Add content pillars before sharing the strategy.")

    selected_platforms = {str(value).strip().lower() for value in foundation.get("platforms") or [] if str(value).strip()}
    if selected_platforms:
        for section in ("platform_playbook", "posting_schedule", "content_ideas"):
            unexpected = {str(item.get("platform") or "").strip() for item in data.get(section) or []
                          if item.get("platform") and str(item.get("platform")).strip().lower() not in selected_platforms}
            if unexpected:
                errors.append(f"{section.replace('_', ' ').title()} includes an unselected platform: {', '.join(sorted(unexpected))}.")

    weekly_plan = data.get("weekly_plan") or []
    planned = len(weekly_plan)
    requested = max(1, min(int(foundation.get("weekly_posts") or brand.weekly_posts_capacity or 3), brand.weekly_posts_capacity))
    if planned != requested:
        errors.append(f"Week one contains {planned} posts but the approved total is {requested}.")
    else:
        passed.append(f"Week one contains exactly {requested} total posts across the selected platforms.")

    scheduled = {}
    for slot in data.get("posting_schedule") or []:
        platform = str(slot.get("platform") or "").strip().lower()
        if platform:
            scheduled[platform] = scheduled.get(platform, 0) + _number(slot.get("frequency"))
    actual = {}
    for post in weekly_plan:
        platform = str(post.get("platform") or "").strip().lower()
        actual[platform] = actual.get(platform, 0) + 1
    if scheduled and scheduled != actual:
        errors.append("Week-one posts do not match the stated number of posts for each platform.")

    kpis = data.get("kpis") or []
    if not kpis or not any(str(item.get("primary_kpi") or "").strip() and str(item.get("monthly_targets") or "").strip() for item in kpis):
        errors.append("Add a primary measure and a target or baseline plan before sharing.")
    else:
        goal_lower = owner_goal.lower()
        kpi_text = " ".join(str(item.get("primary_kpi") or "") for item in kpis).lower()
        goal_signals = (
            (r"\b(?:enquir|lead|dm|message)", r"enquir|lead|dm|message"),
            (r"\b(?:sell|sales|purchases?)", r"sell|sales|purchas|order"),
            (r"\b(?:book|appointment)", r"book|appointment"),
            (r"\b(?:visit|traffic|click)", r"visit|traffic|click"),
        )
        relevant_signals = [kpi_pattern for goal_pattern, kpi_pattern in goal_signals if re.search(goal_pattern, goal_lower)]
        if relevant_signals and not any(re.search(pattern, kpi_text) for pattern in relevant_signals):
            errors.append("The primary KPI does not measure the owner-stated business goal.")

    if data.get("content_ideas"):
        if not any(item.get("hook") and item.get("concept") for item in data["content_ideas"]):
            errors.append("Content ideas need a specific hook and execution concept.")
        if data.get("_ai_provider") and len(data["content_ideas"]) < min(6, requested * 2):
            errors.append("The AI draft has too few content ideas to support the publishing plan.")
        if any(str(item.get("claim_classification") or "").lower() == "evidence_backed" for item in data["content_ideas"]):
            if not (brand.strategy_inputs or {}).get("proof_available") and not _confirmed_claim_evidence(brand):
                errors.append("An idea claims to be evidence-backed, but no brand proof was supplied.")

    if data.get("_generation_mode") == "starter":
        errors.append("This is a basic starter draft. Generate and review a tailored strategy before sharing with a client.")

    percentages = [_number(pillar.get("percentage_of_content") or pillar.get("percentage")) for pillar in data.get("content_pillars") or []]
    if percentages and sum(percentages) != 100:
        errors.append(f"Content pillar percentages total {sum(percentages)} instead of 100.")
    elif percentages:
        passed.append("Content pillar percentages total 100.")
    else:
        warnings.append("Content pillar percentages were not available to validate.")

    unreasoned = [item for item in weekly_plan if not str(item.get("reason") or "").strip()]
    if unreasoned:
        errors.append("Every week-one post needs a reason for earning a publishing slot.")
    else:
        passed.append("Every week-one post includes a strategic reason.")

    sales_text = " ".join(_strategy_strings({
        "executive_summary": data.get("executive_summary"),
        "content_ideas": data.get("content_ideas"),
        "weekly_plan": weekly_plan,
    })).lower()
    if re.search(r"(?:£|\$|₦|€)\s?\d", sales_text) and not (brand.strategy_inputs or {}).get("price_range"):
        errors.append("A price appears in the strategy but no price was confirmed by the brand owner.")
    if re.search(r"\b(?:cures?|treats?|prevents?)\s+acne\b|\bdermatologist approved\b", sales_text) and not _confirmed_claim_evidence(brand):
        errors.append("A medical or expert claim needs verified evidence before it can be shared.")
    claim_hits = [pattern for pattern in UNSUPPORTED_CLAIM_PATTERNS if re.search(pattern, sales_text, re.IGNORECASE)]
    if claim_hits and not _confirmed_claim_evidence(brand):
        errors.append("Potentially unsupported guarantee or proof language was detected. Confirm it before sharing.")
    else:
        passed.append("No obvious unsupported guarantee language was detected.")

    assumptions = foundation.get("assumptions") or []
    if assumptions:
        passed.append("Open assumptions are shown as items needing confirmation.")
    else:
        warnings.append("No open assumptions were recorded; confirm that missing evidence was not silently filled in.")

    status = "blocked" if errors else ("review" if warnings else "passed")
    return {"status": status, "errors": errors, "warnings": warnings, "passed": passed}


def _strategy_strings(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _strategy_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strategy_strings(item)
    elif isinstance(value, (str, int, float)):
        yield str(value)


def _confirmed_claim_evidence(brand):
    return brand.memories.filter(category__in=("offer", "brand_fact"), status="confirmed", evidence__gt="").exclude(source="onboarding").exists()
