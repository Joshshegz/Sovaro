import re

from .ai_service import extract_json_from_llm, generate_with_fallback, tag_ai_provider


PLATFORM_LIMITS = {
    "instagram": "Keep the bio within 150 characters.",
    "tiktok": "Keep the bio concise and within the account's visible character limit.",
    "linkedin": "Optimize the headline and About opening for search, credibility, and conversion.",
    "x": "Keep the bio concise, searchable, and immediately understandable.",
    "youtube": "Make the channel purpose, audience, and content promise clear.",
}

EMOJI_PATTERN = re.compile(
    "[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\U00002600-\U000027BF]+",
    flags=re.UNICODE,
)


def _remove_emojis(value):
    return EMOJI_PATTERN.sub("", str(value or "")).replace("  ", " ").strip()


def _normalize_output(result):
    profile = result.get("optimized_profile") or {}
    for key in ("name_field", "bio", "cta"):
        profile[key] = _remove_emojis(profile.get(key))
    result["optimized_profile"] = profile
    result.setdefault("priority_fix", (result.get("gaps") or ["Make the audience, offer, and next action immediately clear."])[0])
    result.setdefault("missing_information", [])
    result.setdefault("change_explanations", [])
    for item in result.get("alternatives") or []:
        item["bio"] = _remove_emojis(item.get("bio"))
        item["angle"] = _remove_emojis(item.get("angle"))
    return result


def _fallback(data):
    bio = data["current_bio"]
    starting_fresh = not bio
    offer = data["offer"]
    draft_bio = bio or f"Helping {data['audience']} with {offer}."
    has_action = bool(re.search(r"\b(book|shop|buy|join|download|dm|message|visit|learn|start|apply|subscribe)\b", bio, re.I))
    has_market = data["industry"].lower() in bio.lower()
    clarity = 4 if len(bio.split()) <= 35 else 3
    return _normalize_output({
        "analysis_mode": "rule_based",
        "starting_from_scratch": starting_fresh,
        "summary": ("This profile is starting from scratch, so Sovaro created a practical foundation from the brand details." if starting_fresh else "This is a basic structural review because the AI optimizer was unavailable. It checks clarity, discoverability, credibility, and the next action without inventing profile performance."),
        "priority_fix": ("Build the first bio around one audience, one offer, and one next action." if starting_fresh else ("Make the next action explicit." if not has_action else "Make the main search phrase easier to find.")),
        "scorecard": {"clarity": clarity, "discoverability": 4 if has_market else 2, "audience_fit": 3, "credibility": 3, "conversion": 4 if has_action else 2},
        "what_works": [] if starting_fresh else ["The profile states an identity visitors can evaluate."],
        "gaps": (["No current bio exists, so the first version needs a clear audience, offer, and next step."] if starting_fresh else []) + (["The main market keyword is not obvious in the bio."] if not has_market else []) + (["The next action is not explicit."] if not has_action else []),
        "keyword_opportunities": [data["industry"], data["audience"][:60]],
        "missing_information": [item for item, present in (("A verified differentiator", data.get("differentiator")), ("Trust-building proof", data.get("proof_points")), ("A destination link", data.get("destination"))) if not present],
        "optimized_profile": {"name_field": data.get("current_name") or f"{data['business_name']} | {data['industry']}", "bio": draft_bio, "cta": data["desired_cta"]},
        "alternatives": [],
        "action_plan": ["Lead with who the profile helps.", "Add one natural search phrase.", "End with one clear next action."],
        "change_explanations": [
            {"change": "Clarified the audience and offer", "why": "Visitors should understand the relevance before deciding whether to stay."},
            {"change": "Added one direct next action", "why": "A profile should make the conversion path obvious."},
        ],
        "limitations": "No live profile, search ranking, or platform analytics were inspected.",
    })


def suggest_profile_cta(profile_goal, stated_goal="", destination=""):
    """Suggest one editable profile action from the owner's goal and known destination."""
    goal = (stated_goal or "").lower()
    is_whatsapp = "wa.me" in (destination or "").lower() or "whatsapp" in (destination or "").lower()
    if "book" in goal or "appointment" in goal:
        return "Message us on WhatsApp to book" if is_whatsapp else "Ask about booking an appointment"
    if profile_goal == "leads":
        return "Message us on WhatsApp to enquire" if is_whatsapp else "Send an enquiry"
    if profile_goal == "sales":
        return "Ask about available products on WhatsApp" if is_whatsapp else "Explore the offer"
    if profile_goal == "community":
        return "Follow for updates"
    if profile_goal == "authority":
        return "Explore our work"
    return "See what we offer"


def optimize_profile(data):
    platform = data["platform"]
    starting_fresh = not data["current_bio"]
    prompt = f"""
You are a senior social media profile strategist. Audit and rewrite this profile so the right visitor can understand it, find it through platform search, trust it, and know what to do next.

Business or creator name: {data['business_name']}
Industry/category: {data['industry']}
Audience: {data['audience']}
Platform: {platform}
Profile username or URL: {data.get('profile_reference') or 'Not supplied; do not claim to inspect a live profile'}
Profile goal: {data['profile_goal']}
Current name field: {data.get('current_name') or 'None. Create one.'}
Current bio/About: {data['current_bio'] or 'None. Create the first profile bio from the supplied brand context.'}
Current profile category: {data.get('profile_category') or 'Not supplied'}
Destination: {data.get('destination') or 'Not supplied'}
Offer: {data.get('offer') or 'Not supplied; do not invent one'}
Differentiator: {data.get('differentiator') or 'Not supplied; do not invent one'}
Service area: {data.get('service_area') or 'Not supplied'}
Brand voice: {data.get('brand_voice') or 'Not supplied; use a clear neutral tone'}
Claims or topics to avoid: {data.get('claims_to_avoid') or 'None supplied'}
Owner-supplied trust signals: {data.get('proof_points') or 'None supplied; do not invent proof'}
Preferred call to action: {data.get('desired_cta') or 'Not supplied'}

Platform rule: {PLATFORM_LIMITS[platform]}

Rules:
- Use natural customer language and relevant keywords, never keyword stuffing.
- Do not invent awards, customers, results, locations, credentials, features, or proof.
- Follow the supplied brand voice and claims to avoid. Owner-supplied proof is context, not independent verification.
- Explain why each recommendation matters in plain social-media language.
- Treat discoverability and conversion as hypotheses; no live ranking or analytics were inspected.
- The optimized version must be ready to copy.
- If no current bio exists, create a strong first version and do not pretend there was an existing profile to audit.
- Default to zero emojis. Do not add decorative emojis, emoji bullets, or an emoji before every line.
- Use at most one emoji in the entire profile only when the supplied brand style clearly requires it.
- Score from 1 to 5. Scores are profile-quality signals, not performance predictions.

Return ONLY valid JSON:
{{
  "summary": "A direct 1-2 sentence audit verdict without a long introduction",
  "priority_fix": "The single highest-impact profile fix and why it matters",
  "scorecard": {{"clarity": 1, "discoverability": 1, "audience_fit": 1, "credibility": 1, "conversion": 1}},
  "what_works": ["specific strength"],
  "gaps": ["specific weakness and consequence"],
  "missing_information": ["important information that was not supplied; never invent it"],
  "keyword_opportunities": ["natural phrase worth testing"],
  "optimized_profile": {{"name_field": "optimized name", "bio": "complete optimized bio", "cta": "clear CTA"}},
  "alternatives": [{{"angle": "positioning angle", "bio": "complete alternative bio"}}],
  "action_plan": ["highest-priority edit"],
  "change_explanations": [{{"change": "specific edit made", "why": "plain-language reason"}}],
  "limitations": "what this audit cannot prove"
}}
Create exactly two meaningfully different alternatives.
"""
    try:
        response = generate_with_fallback(prompt)
        result = extract_json_from_llm(response.text)
        tag_ai_provider(result, response)
        result["analysis_mode"] = "ai_optimizer"
        result["starting_from_scratch"] = starting_fresh
        for key in ("clarity", "discoverability", "audience_fit", "credibility", "conversion"):
            value = int((result.get("scorecard") or {}).get(key, 1))
            result.setdefault("scorecard", {})[key] = max(1, min(5, value))
        return _normalize_output(result)
    except Exception:
        return _fallback(data)
