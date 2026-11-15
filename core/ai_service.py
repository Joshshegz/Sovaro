import os
import re
import json
import requests
from bs4 import BeautifulSoup
from google import genai
from dotenv import load_dotenv

load_dotenv()


def extract_json_from_llm(text):
    """
    Robust JSON parser for LLM outputs.
    Handles raw JSON, markdown codeblocks (```json ... ```), trailing commentary,
    and extracts outermost JSON object safely.
    """
    if not text:
        raise ValueError("Empty response received from AI model.")

    cleaned = text.strip()

    # 1. Try direct parsing
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    fenced = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
    fenced = re.sub(r'\s*```$', '', fenced, flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        pass

    # 3. Regex match outermost { ... }
    match = re.search(r'(\{[\s\S]*\})', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse valid JSON from AI response: {text[:200]}...")


def clean_and_normalize_strategy(raw_data, requested_hours=4, requested_platforms=None, requested_p_day=None):
    """
    POST-GENERATION VALIDATION & NORMALIZATION PIPELINE:
    Guarantees product-quality and operational consistency:
    1. Validates and normalizes content pillar percentages so they strictly sum to 100%.
    2. Enforces the 4-tier Claim & Evidence Classification on every idea:
       - 'evidence_backed', 'educational', 'hypothetical', 'evidence_required'.
    3. Identifies fabricated first-person experience patterns (e.g., 'We spent X hours', 'We scaled Y to Z')
       and converts them to evidence_required or educational framing.
    4. Segments audience ICP into role tiers and tags assumptions vs verified insights.
    5. Checks cadence feasibility against actual creator hours and core asset repurposing.
    6. Frames platform timings as testable hypotheses rather than dogmatic certainties.
    """
    if not isinstance(raw_data, dict):
        return raw_data

    # --- 1. Pillar Percentages Normalization (Must total 100%) ---
    pillars = raw_data.get("content_pillars") or []
    if isinstance(pillars, list) and len(pillars) > 0:
        parsed_pcts = []
        for p in pillars:
            raw_val = str(p.get("percentage_of_content") or p.get("percentage") or "").strip()
            num_match = re.search(r'(\d+)', raw_val)
            pct_num = int(num_match.group(1)) if num_match else 0
            parsed_pcts.append(pct_num)

        total_pct = sum(parsed_pcts)
        n = len(pillars)
        if total_pct <= 0:
            # Distribute equally
            base = 100 // n
            remainder = 100 - (base * n)
            for i, p in enumerate(pillars):
                val = base + (1 if i < remainder else 0)
                p["percentage_of_content"] = f"{val}%"
        elif total_pct != 100:
            # Re-scale proportionally to strictly hit 100%
            normalized = [round((val / total_pct) * 100) for val in parsed_pcts]
            diff = 100 - sum(normalized)
            if normalized:
                normalized[0] += diff
            for i, p in enumerate(pillars):
                p["percentage_of_content"] = f"{normalized[i]}%"

    # --- 2. Claim & Evidence Classification Engine for Content Ideas ---
    ideas = raw_data.get("content_ideas") or []
    if isinstance(ideas, list):
        fabrication_regex = re.compile(
            r'\b(we spent|we tested|we scaled|we reduced|in our tests|in production for \d+|we built a system that generated \$\d+|we audited \d+|after testing \d+)\b',
            re.IGNORECASE
        )

        for idea in ideas:
            hook = idea.get("hook", "")
            concept = idea.get("concept", "")
            full_text = f"{hook} {concept}"

            existing_class = idea.get("claim_classification")
            # If not classified or invalid, apply classification heuristics
            valid_classes = {"evidence_backed", "educational", "hypothetical", "evidence_required"}
            if not existing_class or existing_class.lower() not in valid_classes:
                if fabrication_regex.search(full_text):
                    # Flag as evidence_required so creator does not publish false first-person claims
                    idea["claim_classification"] = "evidence_required"
                    idea["evidence_note"] = "Requires company verification or real case study proof before publishing first-person claim."
                elif any(word in full_text.lower() for word in ["how to", "why", "breakdown", "guide", "framework", "architecture"]):
                    idea["claim_classification"] = "educational"
                    idea["evidence_note"] = "Explains general engineering/business concepts without unverified first-person claims."
                elif any(word in full_text.lower() for word in ["imagine", "suppose", "example scenario", "hypothetical"]):
                    idea["claim_classification"] = "hypothetical"
                    idea["evidence_note"] = "Illustrative scenario explaining architectural/strategic trade-offs."
                else:
                    idea["claim_classification"] = "educational"
                    idea["evidence_note"] = "Authoritative educational insight."

# Core asset vs adapted asset classification
            if not idea.get("asset_type"):
                fmt = (idea.get("format") or "").lower()
                if any(k in fmt for k in ["carousel", "video", "long-form", "teardown", "whitepaper", "guide"]):
                    idea["asset_type"] = "core_asset"
                else:
                    idea["asset_type"] = "adapted_asset"

            # Content angle & objective fallbacks
            if not idea.get("content_angle"):
                hook_arch = idea.get("hook_archetype", "")
                idea["content_angle"] = hook_arch or "Strategic Perspective"
            if not idea.get("content_objective"):
                funnel = (idea.get("funnel_stage") or "TOFU").upper()
                if "BOFU" in funnel:
                    idea["content_objective"] = "Direct Conversion & Lead Generation"
                elif "MOFU" in funnel:
                    idea["content_objective"] = "Technical Authority & Solution Consideration"
                else:
                    idea["content_objective"] = "Audience Reach & Community Engagement"

    # --- 3. Operational Feasibility & Workload Verification ---
    hours = int(requested_hours or 4)
    # Estimate total weekly workload based on ideas
    core_count = sum(1 for i in ideas if i.get("asset_type") == "core_asset")
    schedule = raw_data.get("posting_schedule") or []

    # Tag posting schedule times as hypotheses
    if isinstance(schedule, list):
        for slot in schedule:
            if not slot.get("confidence_tier"):
                slot["confidence_tier"] = "Empirical Hypothesis (Baseline test - calibrate with 30-day analytics)"

    # Add operational workload assessment
    raw_data["operational_feasibility"] = {
        "allocated_weekly_hours": hours,
        "recommended_core_assets_per_week": max(1, min(4, hours // 2)),
        "recommended_adapted_posts_per_week": max(2, min(8, hours)),
        "workload_status": "feasible" if hours >= 3 else "tight_capacity",
        "workload_summary": (
            f"Calibrated for {hours} hours/week. Focus on producing {max(1, min(4, hours // 2))} deep core asset(s) weekly, "
            f"then repurposing into platform-native adaptations."
        )
    }

    # --- 4. Audience Segment Tagging ---
    icp = raw_data.get("audience_icp_dossier") or {}
    if isinstance(icp, dict) and not icp.get("evidence_basis"):
        icp["evidence_basis"] = "Derived from brand profile and market positioning (assumptions to be calibrated with CRM data)"

    return raw_data


# Models tried in order — if one is overloaded (503) or quota-exceeded (429/RESOURCE_EXHAUSTED),
# the next one is used automatically.
# Uses active Gemini 3.x generation models supported by Google's API.
GEMINI_MODELS = [
    "gemini-3.5-flash",         # Primary — verified active & fast
    "gemini-3.5-flash-lite",    # High-throughput separate quota bucket
    "gemini-3.8-flash",         # Next-gen flash fallback
    "gemini-3-flash-preview",   # Preview tier fallback
    "gemini-flash-latest",      # Alias fallback
]


def get_gemini_client():
    """Initializes and returns the Gemini client using the key from .env"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your .env file.")
    return genai.Client(api_key=api_key)


def generate_with_fallback(prompt):
    """
    Tries each model in GEMINI_MODELS in order.
    Falls back to the next model on:
      - 503 / UNAVAILABLE  (model overloaded)
      - 404 / NOT_FOUND    (model not available on this key)
      - 429 / RESOURCE_EXHAUSTED (daily/minute quota exceeded)
    Raises immediately on bad API key, bad prompt, or any other unrecoverable error.
    Raises only if ALL models fail.
    """
    client = get_gemini_client()
    last_error = None

    for model in GEMINI_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            return response  # Success — return immediately
        except Exception as e:
            error_str = str(e)
            # Retry on availability/quota errors only
            if any(code in error_str for code in [
                "503", "404", "429",
                "UNAVAILABLE", "NOT_FOUND", "RESOURCE_EXHAUSTED",
                "quota", "overloaded"
            ]):
                last_error = e
                continue  # Try next model
            raise  # Any other error (bad API key, invalid request) — raise immediately

    raise Exception(
        f"All Gemini models are currently unavailable or quota-exhausted. "
        f"Last error: {last_error}"
    )



def generate_content_ideas(brand_name, brand_niche, target_audience, tone_of_voice, post_hook, post_content):
    """
    PILLAR 1: STRATEGY & REPURPOSING
    Takes a viral competitor post and adapts it into 3 custom formats for your brand:
    1. TikTok short-form script
    2. LinkedIn thought-leadership post
    3. Instagram carousel outline
    """
    client = get_gemini_client()

    prompt = f"""
You are a Principal Social Media Strategist.

Analyze this viral post:
- Original Hook: {post_hook}
- Content / Transcript: {post_content}

Now adapt this winning concept specifically for OUR brand:
- Brand Name: {brand_name}
- Niche: {brand_niche}
- Target Audience: {target_audience}
- Tone of Voice: {tone_of_voice}

Return a valid JSON object with this exact structure:
{{
  "why_it_worked": "Explanation of the psychological trigger or hook mechanism used in the original post.",
  "ideas": [
    {{
      "target_platform": "tiktok",
      "title": "Short catchy title",
      "hook": "The opening 3-second visual and spoken hook",
      "body_content": "Full video script breakdown with on-screen text and dialogue"
    }},
    {{
      "target_platform": "linkedin",
      "title": "Short catchy title",
      "hook": "The opening 1-2 lines before the 'see more' button",
      "body_content": "Full professional text breakdown with line breaks and takeaway"
    }},
    {{
      "target_platform": "instagram",
      "title": "Short catchy title",
      "hook": "Slide 1 cover title hook",
      "body_content": "Slide-by-slide carousel outline (Slide 1 to Slide 6) plus caption"
    }}
  ]
}}

Return ONLY the raw JSON object. Do not wrap in markdown quotes.
"""

    response = generate_with_fallback(prompt)
    return extract_json_from_llm(response.text)
def generate_monthly_report(brand_name, brand_niche, month_year, metrics_data):
    """
    PILLAR 2: THE REPORTING ENGINE (Arike's Framework)
    Turns monthly analytics into an executive-ready client report:
    1. Executive Summary
    2. 3 Key Insights (The 'Why')
    3. Next Month Strategy (Double Down, Test, Stop)
    """
    prompt = f"""
You are a Senior Social Media Strategist preparing a monthly executive report for a client.

Brand Information:
- Client / Brand Name: {brand_name}
- Industry / Niche: {brand_niche}
- Reporting Period: {month_year}

Monthly Performance Metrics:
{json.dumps(metrics_data, indent=2)}

Generate an executive client report following this exact framework:
1. Executive Summary: 2-3 clear, confident sentences highlighting the primary wins.
2. Key Insights: Exactly 3 analytical observations explaining the 'why' behind the numbers (e.g. why reach grew, what post formats drove saves/shares).
3. Next Month Action Plan:
   - What to Double Down on (repeat what worked)
   - What to Test (new format or angle experiment)
   - What to Stop Doing (drop underperforming efforts)

Return a valid JSON object with this exact structure:
{{
  "executive_summary": "...",
  "key_insights": [
    "Insight 1 explaining the why",
    "Insight 2 explaining the why",
    "Insight 3 explaining the why"
  ],
  "next_month_strategy": {{
    "double_down": "Actionable recommendation",
    "test": "Actionable experiment",
    "stop": "Actionable item to discontinue"
  }}
}}

Return ONLY the raw JSON object. Do not wrap in markdown quotes.
"""

    response = generate_with_fallback(prompt)
    return extract_json_from_llm(response.text)


def analyze_brand_from_url(url):
    """
    PILLAR 0: BRAND INTELLIGENCE
    Takes a website URL, scrapes its content, and uses Gemini to automatically
    infer the full brand profile:
    - Brand name, niche, target audience, tone of voice, brand values
    This allows strategists to onboard a new client with just their website URL.
    """

    # ── Step 1: Fetch the webpage ──────────────────────────────────────────
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Could not fetch the URL '{url}'. Error: {e}")

    # ── Step 2: Parse social links & clean HTML ───────────────────────────
    soup = BeautifulSoup(resp.text, "html.parser")

    # Extract outbound social profile URLs from <a> tags before decomposing
    social_profiles = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        lower_href = href.lower()
        if ("linkedin.com/company/" in lower_href or "linkedin.com/in/" in lower_href) and "linkedin" not in social_profiles:
            social_profiles["linkedin"] = href
        elif ("twitter.com/" in lower_href or "x.com/" in lower_href) and "twitter" not in social_profiles and not any(k in lower_href for k in ["/intent", "/share", "/status"]):
            social_profiles["twitter"] = href
        elif ("youtube.com/" in lower_href or "youtu.be/" in lower_href) and "youtube" not in social_profiles and "/watch" not in lower_href:
            social_profiles["youtube"] = href
        elif "instagram.com/" in lower_href and "instagram" not in social_profiles and "/p/" not in lower_href:
            social_profiles["instagram"] = href
        elif "tiktok.com/" in lower_href and "tiktok" not in social_profiles and "/video/" not in lower_href:
            social_profiles["tiktok"] = href

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    page_title = soup.title.string.strip() if soup.title else ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag["content"].strip() if meta_desc_tag else ""

    body_text = soup.get_text(separator=" ", strip=True)
    body_text = " ".join(body_text.split())
    body_text = body_text[:4000]

    # ── Step 3: Ask Gemini to analyze the brand and social channel strategy ──
    social_context = json.dumps(social_profiles, indent=2) if social_profiles else "None explicitly detected on website."
    prompt = f"""
You are a Principal Social Media Strategist and Market Research Director.

A client has given you the following content scraped from their website: {url}

Page Title: {page_title}
Meta Description: {meta_description}
Detected Outbound Social Profiles:
{social_context}

Website Body Text (first 4000 characters):
{body_text}

Based on the information above, infer this brand's commercial profile AND develop their core social media footprint assessment.

Return a valid JSON object with this exact structure:
{{
  "brand_name": "The brand or company name",
  "niche": "The specific industry or market they operate in (be specific, not generic)",
  "business_model": "b2b_saas / d2c_ecommerce / professional_services / agency / local_business",
  "target_audience": "A detailed description of who their ideal customer is (age, role, pain points, goals)",
  "tone_of_voice": "How they communicate: e.g. 'Professional and authoritative', 'Playful and relatable', 'Bold and motivational'",
  "brand_values": ["value1", "value2", "value3"],
  "content_themes": ["theme1", "theme2", "theme3"],
  "social_profiles": {{
    "linkedin": "Detected or best URL, or empty string",
    "twitter": "Detected or best URL, or empty string",
    "youtube": "Detected or best URL, or empty string",
    "instagram": "Detected or best URL, or empty string",
    "tiktok": "Detected or best URL, or empty string"
  }},
  "social_assessment": {{
    "primary_channels": ["Primary network 1 (e.g. LinkedIn)", "Primary network 2"],
    "secondary_channels": ["Secondary network 1 (e.g. YouTube)"],
    "content_gap_analysis": "1-2 sentences on their biggest missed opportunity on social media",
    "suggested_social_hook_style": "e.g. Technical teardown carousels & executive case study videos"
  }},
  "confidence": "high / medium / low — based on how much useful content was on the page"
}}

Return ONLY the raw JSON object. Do not wrap in markdown quotes.
"""

    response = generate_with_fallback(prompt)
    result = extract_json_from_llm(response.text)

    # Merge detected profiles if AI left any blank
    if "social_profiles" not in result or not isinstance(result["social_profiles"], dict):
        result["social_profiles"] = social_profiles
    else:
        for net, link in social_profiles.items():
            if not result["social_profiles"].get(net):
                result["social_profiles"][net] = link

    return result


def generate_content_strategy(
    brand_name,
    brand_niche,
    target_audience,
    tone_of_voice,
    business_model="b2b_saas",
    primary_goal="Direct Sales & Lead Generation",
    weekly_posts_capacity=3,
    conversion_url="",
    negative_guardrails="",
    brand_values=None,
    content_themes=None,
    target_platforms=None,
    posts_per_day=None,
    posts_per_week=None,
    content_formats=None,
    strategy_inputs=None,
):
    """
    PILLAR 3: STRATEGIC CONTENT PLAYBOOK GENERATOR
    Calibrates channels, pillars, schedule, and ideas against the brand's verified
    commercial objectives, business model, realistic creative capacity, and production format capabilities (talking head, b-roll, carousels, etc.).
    Supports user overrides for target platforms, goals, formats, and daily posting frequency.
    """
    max_weekly_posts = max(1, min(7, int(weekly_posts_capacity or 3)))
    # Used only by the existing workload normalizer; the user is no longer asked to estimate hours.
    estimated_hours = max(2, max_weekly_posts * 2)

    # Process target platforms if provided
    if isinstance(target_platforms, str):
        target_platforms = [p.strip() for p in target_platforms.split(',') if p.strip()]

    if target_platforms and len(target_platforms) > 0:
        platform_clause = (
            f"1. MANDATORY PLATFORMS: The strategy MUST focus exclusively on these user-selected platforms: "
            f"{', '.join(target_platforms)}. Focus all platform playbook analysis, schedule distribution, and content ideas on these networks only."
        )
    else:
        platform_clause = (
            "1. Channel Suitability: Select platforms that strictly fit the business model and target audience "
            "(e.g., if B2B SaaS or Professional Services, prioritize LinkedIn/YouTube/X; if D2C, prioritize visual/video channels)."
        )

    # Honour a weekly target without exceeding the owner-stated posting capacity.
    if posts_per_week is not None:
        weekly_volume = min(int(posts_per_week), max_weekly_posts)
        cadence_clause = (
            f"2. MANDATORY POSTING FREQUENCY: Use {weekly_volume} posts per week. "
            f"The owner-stated ceiling is {max_weekly_posts}; never exceed it."
        )
    elif posts_per_day is not None and str(posts_per_day).strip():
        try:
            p_day = float(posts_per_day)
            weekly_volume = min(max_weekly_posts, max(1, round(p_day * 7)))
            cadence_clause = (
                f"2. MANDATORY POSTING FREQUENCY: Use {weekly_volume} posts per week across all selected networks. "
                f"This respects the owner-stated ceiling of {max_weekly_posts}."
            )
        except (ValueError, TypeError):
            cadence_clause = (
                f"2. Production Feasibility: The brand can sustainably publish up to {max_weekly_posts} posts/week. Your recommended total weekly posting cadence "
                f"across all networks combined MUST NOT EXCEED {max_weekly_posts} posts per week."
            )
    else:
        cadence_clause = (
            f"2. Production Feasibility: The brand can sustainably publish up to {max_weekly_posts} posts/week. Your recommended total weekly posting cadence "
            f"across all networks combined MUST NOT EXCEED {max_weekly_posts} posts per week. Do NOT prescribe unexecutable schedules."
        )

    # Process content formats (Talking head vs faceless B-roll vs carousels vs screen demo vs interactive/memes)
    if isinstance(content_formats, str):
        content_formats = [f.strip() for f in content_formats.split(',') if f.strip()]

    is_flexible_format = not content_formats or any("not sure" in f.lower() or "mixed" in f.lower() or "flexible" in f.lower() for f in content_formats)

    if not is_flexible_format and len(content_formats) > 0:
        format_clause = (
            f"3. STRICT PRODUCTION FORMAT CAPABILITIES: The client/team specified production capabilities: {', '.join(content_formats)}.\n"
            f"- If 'Talking Head / On-Camera' is NOT in this list, DO NOT recommend on-camera videos or personal vlog formats! Focus strictly on faceless, visual, graphic, and text formats (e.g. interactive polls, meme graphics + commentary, multi-slide carousels, screen recordings, code cards, or aesthetic B-roll with text overlay).\n"
            f"- If 'Faceless B-Roll' is specified, prescribe high-retention cinematic stock/b-roll footage with punchy text overlays.\n"
            f"- If 'Screen Recordings & Product Demos' is specified, prescribe software UI walkthroughs, live workflows, or feature teardowns.\n"
            f"- Every idea in the content_ideas array MUST set its 'format' to one aligned with these capabilities."
        )
    else:
        format_clause = (
            "3. DIVERSE PRODUCTION FORMAT MIX: The team's production capability is versatile. "
            "Prescribe a rich, platform-native format variety: interactive polls/quizzes, relatable meme cards/screenshots with witty context, "
            "multi-slide carousels, short-form video clips (faceless B-roll or screencasts), code/teardown cards, customer story spotlights, and text discussions. "
            "Explicitly label each idea's exact format (e.g. 'Interactive 4-Option Poll', 'Meme Image + Story Caption', '6-Slide Carousel', 'Code Walkthrough Screencast', 'Customer Spotlight Card')."
        )

    guardrails_clause = (
        f"- Strict Negative Guardrails (NEVER make these claims): {negative_guardrails}\n"
        if negative_guardrails else ""
    )
    conversion_clause = (
        f"- Primary Conversion Action Destination: {conversion_url}\n"
        if conversion_url else ""
    )
    themes_clause = (
        f"- Verified Content Themes: {', '.join(content_themes)}\n"
        if content_themes else ""
    )
    values_clause = (
        f"- Core Brand Values: {', '.join(brand_values)}\n"
        if brand_values else ""
    )

    prompt = f"""
You are an Enterprise Principal Social Media Strategist and Marketing Operations Architect.

Build a customized, evidence-based, actionable social media strategy for this specific business:
- Brand Name: {brand_name}
- Industry / Niche: {brand_niche}
- Business Model: {business_model} (e.g. B2B SaaS, D2C E-commerce, Professional Services, Local Business, Fintech/Developer Platform)
- Primary Commercial Goal: {primary_goal}
- Target Audience & ICP: {target_audience}
- Tone of Voice: {tone_of_voice}
- Maximum Sustainable Posting Capacity: {max_weekly_posts} posts per week
 - Founder-provided strategy evidence: {json.dumps(strategy_inputs or {}, default=str)}

Use the founder-provided evidence above when choosing platforms, pillars, KPIs, and tactics. Treat missing audit, competitor, audience, or keyword evidence as unknown. Never invent research or numerical targets. A zero budget means recommend free, founder-executable production methods.
The competitor_notes field may contain only names, handles, or links. Treat these as accounts to review, not as completed competitor analysis. Do not claim to have inspected their posts, engagement, or positioning unless observations are explicitly supplied.
If brand_stage is "new", state that there are no past posts to audit, build a first-month launch and measurement plan, and do not imply proven social performance. If posting history is unknown, mark it as unknown rather than assuming a launch or an active account.
{guardrails_clause}{conversion_clause}{themes_clause}{values_clause}

CRITICAL STRATEGIC CONSTRAINTS & EVIDENCE DISCIPLINE:
{platform_clause}
{cadence_clause}
{format_clause}
4. STRICT EVIDENCE-BASED CLAIMS (ZERO FABRICATED AUTHORITY):
   - You MUST NOT invent first-person company history, experiments, benchmarks, client case studies, or quantified metrics that the client never provided (e.g. NEVER generate hooks claiming "We spent 300 hours testing X", "We reduced AWS bills by 84%", "In our 50-client tests").
   - If the brand profile lacks verified experiment metrics, focus hooks on EDUCATIONAL concepts, observable industry architecture, counter-intuitive paradigms, relatable observations, or clearly HYPOTHETICAL scenarios.
   - For every content idea, you must supply:
     * `claim_classification`: EXACTLY one of:
       - 'evidence_backed' (supported by verified company data, documented experiment, or supplied case study)
       - 'educational' (explains a general concept, framework, or system without claiming personal achievement)
       - 'hypothetical' (illustrative scenario explicitly framed as hypothetical)
       - 'evidence_required' (compelling angle that needs client proof/verification before posting)
     * `evidence_note`: 1-sentence note explaining what verified data exists or what the client must supply.
     * `asset_type`: 'core_asset' (deep research, multi-slide teardown, screencast) or 'adapted_asset' (bite-sized platform adaptation derived from a core asset, e.g. poll, meme, single-image take).

5. STRATEGIC CONTENT DIVERSITY & MULTI-DIMENSIONAL MIX:
   Generated strategies must NOT rely solely on dry educational tutorials and promotional feature pitches. You must evaluate and intelligently select from these 7 Core Content Dimensions:
   1) Educational & Informational: High-utility teardowns, tactical guides, frameworks, API/system explainers.
   2) Entertainment, Memes & Relatable Humour: Relatable industry struggles, situational memes, ironic observations, inside jokes of the trade (e.g. Friday deployments, client review loops, payment edge cases).
   3) Community Engagement & Interactive Content: Provocative technical/industry polls, "spot the bug/flaw" quizzes, audience challenges, community spotlights, and UGC prompts.
   4) Product & Service Education: Workflow demonstrations, live UI screencasts, feature teardowns, problem-solution showcases.
   5) Customer Stories & Social Proof: Merchant/client spotlights, transformation case studies, community wins, verified results.
   6) Brand Storytelling & Personality: Behind-the-scenes engineering culture, founder viewpoints, core company principles, team craft.
   7) Trends & Cultural Relevance: Timely commentary on industry shifts, regulatory news, cultural moments adapted intelligently to the niche.

   IMPORTANT CALIBRATION RULE:
   DO NOT force every brand to use all 7 categories equally! Intelligently select and calibrate the relevant mix (typically 3 to 5 core dimensions) based on this specific brand's positioning, audience culture, industry, and commercial objectives.
   - For developer/fintech brands (like Paystack or Stripe): Balance developer education & architecture with relatable developer humor/memes, interactive architecture polls/quizzes, merchant customer stories, and ecosystem trends.
   - For enterprise/high-compliance brands: Dial down memes to dry relatable observations, dial up education, product trust, customer proof, and regulatory trends.
   - For consumer/lifestyle brands: Heavily leverage entertainment, memes, community engagement, and cultural trends.

6. ARCHITECTURAL DISTINCTIONS (PILLARS vs FORMATS vs ANGLES vs OBJECTIVES):
   Maintain strict conceptual separation across these 4 layers:
   - Content Pillars: WHAT the brand discusses (enduring thematic domains / subject areas, e.g., "Developer Experience & API Reliability", "Merchant Growth & Commerce Architecture").
   - Content Formats: HOW the content is presented (media structural vehicle, e.g., "Interactive 4-Option Poll", "Meme Image + Witty Caption", "7-Slide PDF Carousel", "Screencast Walkthrough", "Customer Story Card").
   - Content Angles: THE CREATIVE PERSPECTIVE used (psychological lens, e.g., "Relatable Developer Humour", "Interactive Technical Quiz", "Behind-the-Scenes Architecture", "Customer Milestone Spotlight", "Contrarian Industry Hot Take").
   - Content Objectives: WHAT the content achieves (strategic intent, e.g., "Viral Reach & Brand Affinity", "Technical Trust & Authority", "Direct Merchant Lead Gen", "Community Engagement & Debate").

7. HIGH-SUBSTANCE INTERACTION (NO GENERIC ENGAGEMENT BAIT):
   Interactive and community ideas must NEVER use generic engagement bait like "Agree or disagree?", "Thoughts?", or "Drop a comment below!".
   Instead, design real interactive mechanics:
   - Provide the exact poll question and 4 distinct, polarizing poll options with real industry stakes.
   - Design "Spot the bug / flaw" technical quizzes with specific scenarios.
   - Frame audience challenges with clear prompts and criteria.
   - Propose community spotlight concepts celebrating client or developer work.

8. COMMERCIAL ALIGNMENT & CONTENT PILLARS (PORTFOLIO VS ACQUISITION):
   - Content pillars must reflect the company's customer acquisition priorities while anchoring to their actual broader portfolio.
   - For brands with broad services, distribute strategically across core capabilities without arbitrarily over-indexing 60%+ on a single narrow topic unless explicitly requested.
   - Ensure the percentage allocation of all pillars totals EXACTLY 100%. Explain the commercial acquisition rationale for each pillar.

9. AUDIENCE SEGMENTATION & EVIDENCE BASIS:
   - Separate verified target market traits from strategic inferences.
   - Segment the buyer universe across decision-maker tiers (Technical Decision-Makers vs Business & Operations Leaders).
   - Connect pain points and buying objections to specific role responsibilities.

10. EMPIRICAL PLATFORM SCHEDULING (HYPOTHESIS-BASED):
    - Treat posting times as hypotheses for 30-day baseline testing, not infallible certainties.
    - Never exceed the owner-stated capacity of {max_weekly_posts} posts per week. Use repurposing to keep the plan sustainable.

11. No Generic Buzzwords: Do not use clichés like "game-changer", "supercharge", "in today's fast-paced digital world", "unlock your potential". Be specific, culturally tuned, and grounded.
11A. USER-FACING LANGUAGE: Write every summary, rationale, pillar, KPI, schedule note, and idea for a founder who may not have a social media manager. Use familiar marketing terms such as audience, content pillars, engagement, and KPIs where useful, but explain them in plain words. Avoid unexplained acronyms, technical implementation language, and agency jargon in descriptive text. Keep the required JSON keys and enum values unchanged. Give concrete examples tied to this brand.
12. Conversion Discipline: Align CTAs with the conversion destination ({conversion_url or 'the brand website'}) and the primary commercial goal ({primary_goal}).
13. Hook Psychology: Anchor every idea's hook to one of the 8 Master Hook Archetypes (Contrarian Inversion, Asymmetric Result, High-Effort Extraction, Secret/Gatekeeping, Direct Pain Call-Out, Existential Threat, Relatable Observation, Step-by-Step System).

Return a valid JSON object with this EXACT structure (no deviations):
{{
  "executive_summary": "2-3 crisp, confident sentences articulating the core commercial positioning thesis, portfolio balance, and distribution focus for client executive sign-off.",
  "strategic_assumptions": [
    "Identified assumption 1 (e.g. Assuming primary inbound acquisition prioritizes developer engineering teams over seed founders)",
    "Identified assumption 2 (e.g. Pillar weighting balances developer experience with merchant growth showcases)"
  ],
  "audience_icp_dossier": {{
    "evidence_basis": "Derived from brand profile and market positioning (assumptions to be calibrated with CRM data)",
    "role_segments": [
      {{
        "role_tier": "Technical Leadership (CTO, VP Eng, Lead Architect, Senior Developer)",
        "core_priority": "System stability, architectural scalability, reducing technical debt",
        "primary_friction": "Sprawling infrastructure, fragile pipelines, and endless context switching",
        "buying_objections": ["Implementation risk", "Over-engineered solutions"]
      }},
      {{
        "role_tier": "Executive / Business Leadership (Founder, CEO, COO, Commercial Director)",
        "core_priority": "Predictable velocity, capital efficiency, revenue growth",
        "primary_friction": "Failed payment rates, opaque engineering timelines, talent bottlenecks",
        "buying_objections": ["Uncertain ROI", "Disruption to existing deliverables"]
      }}
    ],
    "category_enemy": "The outdated dogma, bad industry advice, or legacy habit that this brand challenges.",
    "status_desire": "How they want to look competent, forward-thinking, or respected to their boss, board, or peers."
  }},
  "content_pillars": [
    {{
      "name": "Pillar name (WHAT the brand discusses, e.g. API Reliability & Developer Tooling)",
      "description": "What this pillar is about and why it matters commercially for this brand",
      "percentage_of_content": "35%",
      "commercial_rationale": "Why this specific percentage is allocated to drive qualified inbound interest",
      "example_topics": ["topic 1", "topic 2", "topic 3"]
    }}
  ],
  "platform_playbook": [
    {{
      "platform": "Platform Name (e.g. LinkedIn, Twitter / X, Instagram, YouTube)",
      "priority": "Primary / Secondary / Excluded",
      "rationale": "Commercial reason why this platform fits the specific buyer and model",
      "best_content_types": ["Format 1 (e.g. Interactive Polls & Code Teardowns)", "Format 2 (e.g. Meme Graphics + Commentary)"],
      "tone_adjustment": "How tone adapts to native platform culture"
    }}
  ],
  "content_mix": {{
    "educational_informational": "30% — tactical guides, architecture breakdowns",
    "entertainment_humour": "20% — relatable memes, situational developer humor, daily industry struggles",
    "community_interactive": "20% — high-stakes debate polls, quizzes, community spotlights",
    "product_service_education": "15% — API feature releases, webhook reliability walkthroughs",
    "customer_proof_stories": "15% — customer scaleup growth stories, merchant transformation showcases"
  }},
  "posting_schedule": [
    {{
      "platform": "Platform Name",
      "frequency": "e.g. 2x per week (never above {max_weekly_posts} total weekly posts)",
      "best_days": ["Tuesday", "Thursday"],
      "best_times": "8:00 AM - 10:00 AM local time",
      "confidence_tier": "Empirical Hypothesis (Baseline test - calibrate with 30-day analytics)",
      "rationale": "Why this cadence is sustainable and matches audience habits"
    }}
  ],
  "content_ideas": [
    {{
      "idea_number": 1,
      "pillar": "Parent Content Pillar name (WHAT)",
      "platform": "Target Platform",
      "funnel_stage": "TOFU (Awareness) / MOFU (Consideration) / BOFU (Conversion)",
      "format": "Specific Format (HOW, e.g. Interactive 4-Option Poll, Meme Image + Story, 7-Slide Carousel, Screencast Teardown, Customer Spotlight)",
      "content_angle": "Creative Angle (PERSPECTIVE, e.g. Relatable Developer Humour, Interactive Technical Quiz, Behind-the-Scenes Architecture, Customer Milestone Spotlight, Contrarian Hot Take)",
      "content_objective": "Strategic Intent (OBJECTIVE, e.g. Viral Reach & Brand Affinity, Technical Authority, Direct Trial / Signup, Community Engagement)",
      "asset_type": "core_asset (or adapted_asset)",
      "claim_classification": "educational (or evidence_backed, hypothetical, evidence_required)",
      "evidence_note": "Explains general architecture concept without unsupported first-person claims.",
      "hook_archetype": "e.g. Contrarian Inversion, High-Effort Extraction, Direct Pain Call-Out, Relatable Observation",
      "hook": "The exact opening headline, visual meme caption, or provocative poll question",
      "concept": "Specific, actionable content breakdown. For memes, describe the visual and witty text. For polls/quizzes, provide the exact question and options. For teardowns, outline the key steps.",
      "suggested_cta": "Specific call to action tailored to the angle and objective (e.g. Vote in the poll, Save for sprint planning, or Explore the docs at {conversion_url or brand_name})"
    }}
  ],
  "kpis": [
    {{
      "platform": "Platform Name",
      "primary_kpi": "e.g. Outbound Link Clicks to /signup",
      "secondary_kpis": ["Content Saves", "Poll Votes & Comments"],
      "monthly_targets": "e.g. Establish 30-day baseline, then target 15% MoM expansion",
      "what_to_watch": "The key utility metric indicating whether content is resonating"
    }}
  ],
  "cta_strategy": [
    {{
      "awareness_stage": "Cold (Unaware / Problem-Aware)",
      "goal": "Build brand affinity, earn high-intent bookmarks and viral shares",
      "cta_examples": ["Vote in the poll below — which architecture pattern does your team use?"],
      "platforms": ["LinkedIn", "Twitter / X"]
    }},
    {{
      "awareness_stage": "Warm (Consideration / Solution-Aware)",
      "goal": "Drive traffic to explore the product solution and documentation",
      "cta_examples": ["Explore our technical documentation and API sandbox (Link in comments)."],
      "platforms": ["LinkedIn", "Twitter / X"]
    }},
    {{
      "awareness_stage": "Hot (Conversion / Decision-Ready)",
      "goal": "Direct conversion to primary destination",
      "cta_examples": ["Create your free Paystack merchant account at {conversion_url or brand_name}."],
      "platforms": ["LinkedIn", "Twitter / X"]
    }}
  ]
}}

Generate exactly 30 content ideas in the content_ideas array.
Ensure a rich distribution of creative angles across the 30 ideas:
- Include relatable memes, situational humor, and cultural inside jokes.
- Include interactive content with real stakes (polls with 4 options, scenario quizzes, community spotlights).
- Include deep technical and product teardowns.
- Include merchant/customer stories and social proof.
Return ONLY the raw JSON object. Do not wrap in markdown quotes.
"""

    response = generate_with_fallback(prompt)
    raw_strategy = extract_json_from_llm(response.text)
    return clean_and_normalize_strategy(
        raw_strategy,
        requested_hours=estimated_hours,
        requested_platforms=target_platforms,
        requested_p_day=posts_per_day
    )


def assist_strategy_field(
    brand_name,
    brand_niche,
    target_audience,
    tone_of_voice,
    business_model="b2b_saas",
    field_type="goal",
    extra_context=None,
):
    """
    AI Copilot for Manual Strategy Builder:
    Assists the user in drafting specific strategy elements when they don't know what to put:
    - 'goal': suggests an evidence-based, commercially grounded campaign goal
    - 'pillars': suggests 3-4 structured content pillars with percentages and descriptions
    - 'mix': suggests a balanced content mix breakdown calibrated to the business model
    - 'ideas': generates 3 high-impact content hooks/concepts for selected platforms
    """
    extra_context = extra_context or {}

    if field_type == "goal":
        prompt = f"""
You are an Enterprise Social Media Strategist.
Suggest ONE sharp, measurable commercial strategy goal for this business:
Brand: {brand_name}
Industry/Niche: {brand_niche}
Target Audience: {target_audience}
Business Model: {business_model}
Tone: {tone_of_voice}

The goal must be commercially grounded (e.g. booked demos, direct sales, community trust, qualified trial signups).
Return a valid JSON object:
{{
  "suggested_goal": "e.g. Generate 30 high-intent enterprise pipeline demos per month via problem teardowns and ROI case studies"
}}
Return ONLY valid JSON.
"""
    elif field_type == "pillars":
        prompt = f"""
You are an Enterprise Social Media Strategist.
Suggest 3 to 4 distinct, authoritative content pillars for this business:
Brand: {brand_name}
Industry/Niche: {brand_niche}
Target Audience: {target_audience}
Business Model: {business_model}
Tone: {tone_of_voice}

Return a valid JSON object:
{{
  "pillars": [
    {{
      "name": "Pillar Name (e.g. Problem Architecture & System Teardowns)",
      "percentage": "35%",
      "description": "Specific focus and customer problem solved"
    }}
  ]
}}
Ensure percentages sum to 100%. Return ONLY valid JSON.
"""
    elif field_type == "mix":
        prompt = f"""
You are a Social Media Content Strategist.
Recommend the optimal content mix percentage breakdown for a {business_model} business in {brand_niche}:
Return a valid JSON object:
{{
  "mix": {{
    "educational": "e.g. 40% Tactical guides & breakdowns",
    "authority": "e.g. 30% Case studies & performance proof",
    "social_proof": "e.g. 20% Client wins & testimonials",
    "conversion": "e.g. 10% Direct offers & audits"
  }}
}}
Return ONLY valid JSON.
"""
    elif field_type == "ideas":
        platforms = extra_context.get("platforms", ["LinkedIn", "Twitter / X"])
        if isinstance(platforms, list):
            platforms_str = ", ".join(platforms)
        else:
            platforms_str = str(platforms)
        current_goal = extra_context.get("goal", "Customer acquisition")
        formats = extra_context.get("formats", [])
        if isinstance(formats, list) and len(formats) > 0:
            format_line = f"Allowed Formats: Strictly design hooks for: {', '.join(formats)}. (If 'Talking Head' is absent, focus strictly on faceless B-roll, text carousels, or screen recordings)."
        else:
            format_line = "Allowed Formats: Versatile mix (faceless B-roll clips, carousels, or screen recordings)."

        prompt = f"""
You are a Social Media Copywriter and Strategist.
Generate 3 high-impact, scroll-stopping content hooks and concepts for {brand_name} ({brand_niche}):
Target Audience: {target_audience}
Target Platforms: {platforms_str}
Goal: {current_goal}
{format_line}

Do not use clichés like 'supercharge' or 'game-changer'. Be specific, contrarian, and value-driven.
Return a valid JSON object:
{{
  "ideas": [
    {{
      "platform": "LinkedIn",
      "format": "e.g. Faceless B-Roll, 7-Slide Carousel, Screen Demo, Talking Head",
      "hook": "The exact opening headline or line 1",
      "concept": "Brief explanation of what the post demonstrates"
    }}
  ]
}}
Return ONLY valid JSON.
"""
    else:
        raise ValueError(f"Unknown field_type: {field_type}")

    response = generate_with_fallback(prompt)
    return extract_json_from_llm(response.text)


def analyze_competitor_socials(
    brand_name,
    brand_niche,
    competitor_name,
    competitor_url="",
    social_handles=None,
    brand_context="",
):
    """
    COMPETITOR SOCIAL INTELLIGENCE ENGINE
    Analyzes what a competitor does across social channels and what works for them,
    grounded in web scraping (if URL provided) and advanced social media intelligence prompting.
    Surfaces:
      - What they do (content positioning, posting rhythm, platform roles, core themes)
      - What works for them (viral hooks, high-resonance formats, engagement triggers)
      - Winning hook patterns (psychological angle, hook formula, sample lines)
      - Top content formats (e.g. 10-slide teardowns, founder screencasts, contrarian takes)
      - Platform-by-platform tactical breakdown (LinkedIn, Instagram, TikTok, X/Twitter, YouTube)
      - White-space / Differentiation opportunities for your brand to out-execute them
    """
    web_context = ""
    if competitor_url and competitor_url.startswith(('http://', 'https://')):
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            res = requests.get(competitor_url, headers=headers, timeout=5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                title = soup.title.string.strip() if soup.title else ""
                desc_tag = soup.find("meta", attrs={"name": "description"})
                desc = desc_tag["content"].strip() if desc_tag else ""
                text_content = " ".join(soup.get_text(separator=" ", strip=True).split())[:2500]
                web_context = f"\nCompetitor Website Data ({competitor_url}):\nTitle: {title}\nDescription: {desc}\nPage Text Snippet: {text_content}\n"
        except Exception:
            web_context = f"\nCompetitor Website: {competitor_url} (Could not scrape live, analyze based on brand identity and domain).\n"

    # Format handles if given
    handles_str = ""
    if social_handles and isinstance(social_handles, dict):
        active_handles = [f"{platform.upper()}: {handle}" for platform, handle in social_handles.items() if handle]
        if active_handles:
            handles_str = f"Competitor Social Handles / Profiles:\n" + "\n".join(active_handles)
    elif social_handles and isinstance(social_handles, str):
        handles_str = f"Competitor Social Presence: {social_handles}"

    prompt = f"""
You are an Elite Social Media Intelligence Director and Competitive Strategist.

Analyze this competitor for our client's brand:
- Our Brand: {brand_name}
- Our Niche / Industry: {brand_niche}
{f'- Our Brand Context: {brand_context}' if brand_context else ''}

COMPETITOR UNDER AUDIT:
- Competitor Name: {competitor_name}
{web_context}
{handles_str}

Conduct a comprehensive social media audit across ALL major social networks (LinkedIn, Instagram, TikTok, X / Twitter, YouTube).
Focus specifically on CURRENT, ACTIVE content strategies. If a competitor has abandoned a platform or posts infrequently, explicitly highlight that as a competitive weakness/opportunity for our brand in the audit.
Answer the two most critical questions social media managers need to know:
1. WHAT DO THEY DO? (Their content strategy, themes, aesthetic, visual cadence, brand tone)
2. WHAT WORKS FOR THEM? (Their viral triggers, highest-converting content formats, audience psychology, and winning hooks)
3. HOW OUR BRAND WINS? (The whitespace opportunities, what they neglect, and tactical ways to differentiate and capture their audience)

You MUST return a valid JSON object matching this EXACT schema:
{{
  "competitor_name": "{competitor_name}",
  "primary_channels": ["LinkedIn", "Instagram", "TikTok", "X / Twitter", "YouTube"],
  "posting_cadence_summary": "e.g. High volume LinkedIn (5x/wk) + Curated Instagram Reels (3x/wk)",
  "what_they_do": "Comprehensive 3-4 sentence breakdown of their core strategy: what themes they post about, their visual/editorial style, who they target, and how they position their solution.",
  "what_works": "Detailed 3-4 sentence breakdown of their highest-performing assets: what gets them the most comments/saves/shares, their psychological triggers (e.g. vulnerability, teardowns, contrarian hot takes), and audience engagement mechanisms.",
  "top_content_formats": [
    "e.g. 8-10 Slide Educational Carousels with bold typographic title cards",
    "e.g. 45-60s Screencast Teardowns exposing messy industry workflows",
    "e.g. Contrarian Data Visualizations with spicy 1-line commentary"
  ],
  "winning_hook_patterns": [
    "e.g. 'We spent $50,000 testing [X] so you don't have to — here is the brutal truth:'",
    "e.g. 'Stop doing [Common Practice]. Top 1% teams switched to this 3-step system:'",
    "e.g. 'Unpopular opinion: [Niche Myth] is costing you [Pain Point]. Here is what actually works:'",
    "e.g. 'I analyzed 100+ [Examples] to find the secret pattern everyone is missing:'"
  ],
  "channel_breakdown": {{
    "linkedin": {{
      "focus": "Brief summary of what they do here",
      "what_works": "Specific tactic that drives engagement on this platform"
    }},
    "instagram": {{
      "focus": "Brief summary of what they do here",
      "what_works": "Specific tactic that drives engagement on this platform"
    }},
    "tiktok": {{
      "focus": "Brief summary of what they do here",
      "what_works": "Specific tactic that drives engagement on this platform"
    }},
    "x_twitter": {{
      "focus": "Brief summary of what they do here",
      "what_works": "Specific tactic that drives engagement on this platform"
    }},
    "youtube": {{
      "focus": "Brief summary of what they do here",
      "what_works": "Specific tactic that drives engagement on this platform"
    }}
  }},
  "differentiation_opportunities": "Concrete, tactical roadmap of whitespace: what this competitor is failing to do, their content gaps, and how {brand_name} can create 10x better content to dominate the niche.",
  "swot_analysis": {{
    "strengths": ["Key social media advantage 1", "Key social media advantage 2"],
    "weaknesses": ["Where their content falls short or fails to connect", "Major gap in their posting"],
    "opportunities": ["Unmet audience demand that your brand can capitalize on", "Angle they are neglecting"],
    "threats": ["Where they could crowd out your reach if ignored", "Their strongest competitive moats"]
  }},
  "key_takeaway_for_brand": "1-2 sentence executive punchline summarizing how to outflank them."
}}

Return ONLY valid JSON. Do not include markdown code block ticks.
"""

    response = generate_with_fallback(prompt)
    return extract_json_from_llm(response.text)


def discover_competitors_for_brand(
    brand_name,
    brand_niche,
    target_audience="",
    business_model="",
    conversion_url="",
):
    """
    AI COMPETITOR DISCOVERY ENGINE
    Solves the 'blank page' problem when a founder or social media manager doesn't
    know their competitors off the top of their head.
    Identifies 4-5 top competitors, benchmark brands, or adjacent category leaders
    with established social media distribution.
    """
    prompt = f"""
You are an Elite Social Media Market Intelligence Director and Industry Analyst.

Our client's brand is:
- Brand Name: {brand_name}
- Niche / Industry: {brand_niche}
- Target Audience: {target_audience or 'Target customers in this sector'}
- Business Model: {business_model or 'Modern digital business'}
{f'- Website: {conversion_url}' if conversion_url else ''}

The client needs to identify their real competitors on social media.
CRITICAL REQUIREMENT - ACTIVE SOCIAL MEDIA PRESENCE:
Every competitor you suggest MUST BE ACTIVELY POSTING on social media recently (within the last 30 to 60 days).
Do NOT suggest dormant accounts, zombie startups, or companies whose social media profiles haven't posted in 6 to 12+ months.
Prioritize competitors that currently publish content on LinkedIn, Instagram, TikTok, X (Twitter), or YouTube with observable audience engagement.

Identify 4 to 5 well-known, high-performing DIRECT competitors and active alternative solution providers that operate in the SAME market and solve the same core problem for customers.
Do NOT include cross-industry inspiration accounts or unrelated developer tools (e.g., if the brand is payments/fintech, suggest Adyen, PayPal, Square, Paddle, Braintree; do NOT suggest unrelated dev tools like Vercel or Figma).

For each competitor, provide:
1. `name`: Real company or brand name
2. `website`: Website URL or domain (e.g. "https://adyen.com")
3. `handle`: Primary social handle or username (e.g. "@adyen")
4. `primary_platform`: The main social network where they get the most attention ('linkedin', 'instagram', 'tiktok', 'twitter', or 'youtube')
5. `category_type`: 'Direct Competitor' or 'Indirect Competitor / Alternative'
6. `why_study_them`: 1-2 punchy sentences on how they position against similar products on social media and what works for them
7. `estimated_socials`: list of channels where they are active (e.g. ["LinkedIn", "X / Twitter", "YouTube"])

Return a valid JSON object matching this schema:
{{
  "competitors": [
    {{
      "name": "...",
      "website": "https://...",
      "handle": "@...",
      "primary_platform": "linkedin",
      "category_type": "Direct Competitor",
      "why_study_them": "...",
      "estimated_socials": ["LinkedIn", "Instagram", "X / Twitter"]
    }}
  ]
}}

Return ONLY valid JSON.
"""

    response = generate_with_fallback(prompt)
    return extract_json_from_llm(response.text)
