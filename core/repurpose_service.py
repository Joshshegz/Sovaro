import re

from .ai_service import extract_json_from_llm, generate_with_fallback


PLATFORM_RULES = {
    "linkedin": "A strong first two lines, scannable professional body, useful insight, restrained CTA. No fake personal story.",
    "instagram": "A concise caption plus a carousel or Reel concept. The cover/first-frame hook must be short and visual.",
    "tiktok": "A first-frame visual, spoken hook, on-screen text, conversational short-form script, shot list, and caption.",
    "x": "A concise standalone post or short thread. Put the sharpest insight first; avoid filler and unnecessary hashtags.",
    "threads": "Conversational, opinionated but natural. One clear idea with an easy discussion prompt.",
}

SLOP_PATTERNS = {
    "generic AI phrasing": r"\b(in today'?s fast[- ]paced|ever[- ]evolving|delve into|unlock the power|game[- ]changer|revolutioni[sz]e|elevate your|navigate the complexities)\b",
    "empty contrast formula": r"\bit'?s not (?:just )?.{1,70}[,;—-] it'?s .{1,90}",
    "generic announcement": r"\b(excited to (?:announce|share)|we are thrilled)\b",
    "hype without evidence": r"\b(guaranteed|skyrocket|explode your|secret sauce|ultimate solution)\b",
}


def _quality_audit(source, outputs):
    source_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", source))
    warnings = []
    for output in outputs:
        combined = " ".join(str(output.get(key, "")) for key in ("hook", "body", "caption", "cta"))
        for label, pattern in SLOP_PATTERNS.items():
            if re.search(pattern, combined, re.IGNORECASE):
                warnings.append({"platform": output.get("platform", "Unknown"), "type": label, "message": f"Review {label} before publishing."})
        added_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", combined)) - source_numbers
        if added_numbers:
            warnings.append({
                "platform": output.get("platform", "Unknown"),
                "type": "number not found in source",
                "message": f"Verify added number(s): {', '.join(sorted(added_numbers))}.",
            })
    return {
        "status": "review_required" if warnings else "clean_draft",
        "warnings": warnings,
        "checks": ["generic-language scan", "unsupported-number scan", "source-fidelity instruction", "platform-native instruction"],
    }


def generate_repurpose_package(brand, cleaned_data):
    platforms = cleaned_data["platforms"]
    rules = "\n".join(f"- {platform}: {PLATFORM_RULES[platform]}" for platform in platforms)
    mode_instruction = (
        "Extract and preserve the source's real argument, examples, voice, and evidence."
        if cleaned_data["mode"] == "repurpose"
        else "Treat the short input as a seed. Develop useful caption directions without inventing facts, results, experience, or customer evidence."
    )
    source = cleaned_data["source_content"][:16000]
    prompt = f"""
You are a senior social media copywriter and content repurposing editor.

Brand: {brand.name}
Market: {brand.niche}
Audience: {brand.target_audience}
Voice: {brand.tone_of_voice}
Business goal: {brand.primary_goal}
Guardrails: {brand.negative_guardrails or 'No additional guardrails supplied'}
Content objective: {cleaned_data['objective']}
Desired audience action: {cleaned_data.get('desired_action') or 'Choose a low-friction action appropriate to the objective'}
Mode: {cleaned_data['mode']}

SOURCE OR IDEA:
{source}

{mode_instruction}

Quality rules:
- Do not use generic AI phrases such as “in today's fast-paced world”, “unlock the power”, “game-changer”, “delve into”, or “elevate your”.
- Avoid the tired “It's not X, it's Y” construction unless the source naturally uses that contrast.
- Do not invent statistics, customer stories, experiments, outcomes, quotations, product features, or first-person experience.
- Do not promise virality. Hooks must be clear, specific, source-supported, and fulfilled by the body.
- Preserve the brand voice, but do not imitate another creator.
- Use zero hashtags unless they genuinely improve discovery; never add more than five.
- Write complete publishable drafts, not advice about what the user could write.

Platform requirements:
{rules}

Return ONLY valid JSON in this exact structure:
{{
  "source_analysis": {{
    "central_thesis": "core meaning",
    "audience_problem": "problem addressed",
    "strongest_insights": ["insight"],
    "stories_or_examples": ["only examples actually in source"],
    "verified_claims": ["claims directly supported by source"],
    "claims_to_verify": ["anything that needs evidence"],
    "voice_cues": ["observable voice characteristic"]
  }},
  "hook_options": [
    {{
      "hook": "hook text",
      "type": "problem/contrarian/framework/story/question/specific outcome",
      "why_it_works": "brief rationale",
      "scores": {{"audience_fit": 1, "clarity": 1, "specificity": 1, "tension": 1, "payoff": 1, "source_fidelity": 1}},
      "total": 6
    }}
  ],
  "outputs": [
    {{
      "platform": "one selected platform",
      "format": "native format",
      "hook": "final hook",
      "body": "complete platform-native body or script",
      "caption": "publishable caption, or concise supporting copy where appropriate",
      "cta": "specific next action",
      "visual_direction": "carousel slides, first frame and shot list, or visual treatment",
      "source_basis": ["source insight used"],
      "claim_flags": ["verification warning, empty if none"],
      "alternative_hooks": ["alternative 1", "alternative 2"]
    }}
  ]
}}

Create exactly five distinct hook options overall and exactly one complete output for each selected platform: {', '.join(platforms)}.
Score each hook dimension from 1 to 5 and set total to the sum out of 30.
"""
    response = generate_with_fallback(prompt)
    data = extract_json_from_llm(response.text)
    outputs = data.get("outputs") or []
    selected = set(platforms)
    aliases = {"twitter": "x", "x (twitter)": "x"}
    normalized_outputs = []
    for item in outputs:
        platform = str(item.get("platform", "")).strip().lower()
        platform = aliases.get(platform, platform)
        if platform in selected:
            item["platform"] = "X" if platform == "x" else platform.title()
            normalized_outputs.append(item)
    outputs = normalized_outputs
    if not outputs:
        raise ValueError("The AI did not return usable platform drafts.")
    data["outputs"] = outputs
    data["quality_report"] = _quality_audit(source, outputs)
    return data
