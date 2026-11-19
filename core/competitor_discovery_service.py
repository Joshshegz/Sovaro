import json

from google.genai import types

from .ai_service import GEMINI_MODELS, extract_json_from_llm, get_gemini_client


SOCIAL_HOSTS = {
    "Instagram": ("instagram.com",),
    "TikTok": ("tiktok.com",),
    "LinkedIn": ("linkedin.com",),
    "YouTube": ("youtube.com", "youtu.be"),
    "Facebook": ("facebook.com",),
    "X": ("x.com", "twitter.com"),
}


def _valid_platform(item):
    platform = str(item.get("platform") or "").strip()
    url = str(item.get("url") or "").strip()
    evidence = str(item.get("recent_activity_evidence") or "").strip()
    recent_posts = item.get("recent_posts_found", 0)
    try:
        recent_posts = int(recent_posts)
    except (TypeError, ValueError):
        recent_posts = 0
    hosts = SOCIAL_HOSTS.get(platform, ())
    return platform and url.startswith(("http://", "https://")) and any(host in url.lower() for host in hosts) and evidence and recent_posts >= 2


def discover_active_competitors(brand_name, industry, audience="", location=""):
    prompt = f"""
Use Google Search to find direct competitors or close substitute brands for this business.

Brand: {brand_name or 'New brand'}
Industry: {industry}
Audience: {audience or 'Not supplied'}
Location or market: {location or 'Not supplied'}

STRICT ELIGIBILITY RULE:
- Return a company only when public search results show at least TWO posts within the last 10 days on each of at least TWO different social platforms.
- Include the direct social profile URL and a concise description of the recent activity found for each platform.
- Do not count a website, directory, app-store listing, or the same social network twice.
- Do not infer activity from follower counts or the existence of a profile.
- Prefer direct competitors serving the same audience and market. Close substitutes must be labelled.
- If the evidence is insufficient, omit the company. Returning an empty list is correct.

Return ONLY JSON:
{{
  "competitors": [
    {{
      "name": "Company name",
      "relationship": "direct competitor or close substitute",
      "why_relevant": "One sentence",
      "platforms": [
        {{"platform": "Instagram", "url": "https://...", "recent_posts_found": 2, "last_seen": "date or relative date", "recent_activity_evidence": "What recent public activity was found"}},
        {{"platform": "LinkedIn", "url": "https://...", "recent_posts_found": 2, "last_seen": "date or relative date", "recent_activity_evidence": "What recent public activity was found"}}
      ]
    }}
  ],
  "limitations": ["Any specific search limitation"]
}}
"""
    client = get_gemini_client()
    last_error = None
    for model in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
            )
            data = extract_json_from_llm(response.text)
            verified = []
            for candidate in data.get("competitors") or []:
                platforms = [item for item in candidate.get("platforms") or [] if _valid_platform(item)]
                distinct = {item["platform"] for item in platforms}
                if len(distinct) < 2:
                    continue
                candidate["platforms"] = platforms
                candidate["verification_status"] = "Recent activity found on at least two social platforms"
                verified.append(candidate)
            return {
                "competitors": verified[:5],
                "limitations": data.get("limitations") or [],
                "source_status": "grounded",
            }
        except Exception as exc:
            last_error = exc
            if any(token in str(exc) for token in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "quota", "overloaded")):
                continue
            raise
    raise RuntimeError(f"Grounded competitor search is temporarily unavailable: {last_error}")
