import re

from .ai_service import extract_json_from_llm, generate_with_fallback


def _fallback_analysis(caption, platform, has_metrics):
    words = caption.split()
    first_line = next((line.strip() for line in caption.splitlines() if line.strip()), caption[:120])
    has_question = "?" in first_line
    has_number = bool(re.search(r"\b\d+(?:\.\d+)?%?\b", first_line))
    has_cta = bool(re.search(r"\b(comment|reply|share|save|follow|click|visit|download|join|book|tell me|dm)\b", caption, re.I))
    hook_score = 4 if (has_question or has_number or len(first_line.split()) <= 14) else 3
    clarity_score = 4 if len(words) <= 300 else 3
    cta_score = 4 if has_cta else 2
    return {
        "analysis_mode": "rule_based",
        "verdict_label": "Observed performance review" if has_metrics else "Potential effectiveness review",
        "summary": "This is a structural review of the writing. The live AI coach was unavailable, so use these findings as a practical first pass rather than a complete explanation.",
        "purpose": "The post appears designed to earn attention, communicate one idea, and move readers toward a response.",
        "hook": {"type": "Question or specificity" if (has_question or has_number) else "Direct opening", "why_it_may_work": f"The opening begins with “{first_line[:110]}”. It gives the reader an immediate entry point.", "risk": "Make sure the body delivers exactly what the opening promises."},
        "strengths": ["The post has a visible opening line.", "Its main message can be evaluated without extra context."],
        "weaknesses": (["The next action is not explicit; readers may understand the post but do nothing."] if not has_cta else ["Check that the requested action is the easiest logical next step."]),
        "improvements": ["Make the opening more specific to one reader problem.", "Remove any sentence that repeats the previous point.", "End with one clear, low-friction action."],
        "scorecard": {"hook": hook_score, "clarity": clarity_score, "relevance": 3, "credibility": 3, "cta": cta_score},
        "platform_fit": f"Review the length, rhythm, and first-line payoff against normal {platform.title()} reading behaviour.",
        "performance_interpretation": "Metrics were supplied, but the fallback cannot reliably attribute results to individual writing choices." if has_metrics else "No performance data was supplied, so this analysis does not claim the caption worked.",
        "rewrite": caption,
        "rewrite_notes": ["The original is preserved because a reliable AI rewrite was unavailable."],
    }


def analyze_caption(brand, cleaned_data):
    caption = cleaned_data["caption"]
    platform = cleaned_data["platform"]
    performance = (cleaned_data.get("performance_context") or "").strip()
    evidence_instruction = (
        "Use the supplied performance context as observed evidence, but describe contribution as likely—not proven causation."
        if performance else
        "No metrics were supplied. Never say the caption worked, performed well, went viral, or caused an outcome. Discuss only why it may be effective."
    )
    brand_context = (
        f"Brand: {brand.name}\nMarket: {brand.niche}\nAudience: {brand.target_audience}\nBrand voice: {brand.tone_of_voice}"
        if brand else
        "Brand context: Not supplied. Judge only the pasted writing and do not invent a brand, audience, offer, or voice."
    )
    prompt = f"""
You are a senior social media copy coach. Teach the user how to recognise strong writing; do not merely grade it.

{brand_context}
Platform: {platform}
Performance context: {performance or 'None supplied'}

POST TO ANALYSE:
{caption}

{evidence_instruction}

Rules:
- Explain mechanisms in plain industry language: hook, tension, specificity, proof, pacing, payoff, CTA and platform fit.
- Separate observable writing choices from assumptions about audience reaction.
- Do not infer impressions, engagement, intent, audience sentiment or conversion without evidence.
- Flag unsupported statistics, vague claims, clickbait, buried payoff, generic AI phrasing and mismatched CTAs.
- Preserve the author's meaning and voice in the rewrite. Do not invent facts, stories, results or expertise.
- Scores are coaching signals, not predictions of reach.

Return ONLY valid JSON:
{{
  "verdict_label": "Potential effectiveness review or Observed performance review",
  "summary": "2 sentence teaching summary",
  "purpose": "what the post is trying to achieve",
  "hook": {{"type": "hook type", "why_it_may_work": "mechanism", "risk": "limitation"}},
  "strengths": ["specific strength and why it matters"],
  "weaknesses": ["specific weakness and its effect"],
  "improvements": ["specific edit the writer can make"],
  "scorecard": {{"hook": 1, "clarity": 1, "relevance": 1, "credibility": 1, "cta": 1}},
  "platform_fit": "platform-specific assessment",
  "performance_interpretation": "careful interpretation based on supplied evidence",
  "rewrite": "complete improved post",
  "rewrite_notes": ["what changed and why"]
}}
Score every scorecard item from 1 to 5.
"""
    try:
        response = generate_with_fallback(prompt)
        data = extract_json_from_llm(response.text)
        data["analysis_mode"] = "ai_coach"
        for key in ("hook", "clarity", "relevance", "credibility", "cta"):
            value = int((data.get("scorecard") or {}).get(key, 1))
            data.setdefault("scorecard", {})[key] = max(1, min(5, value))
        return data
    except Exception:
        return _fallback_analysis(caption, platform, bool(performance))
