"""Generate editable audience hypotheses for the brand setup form."""

from .ai_service import extract_json_from_llm, generate_with_fallback


def _starter_suggestion(niche, business_model, primary_goal):
    audience_by_model = {
        "b2b_saas": f"Decision-makers and day-to-day users in organisations that need a better way to handle {niche}",
        "d2c_ecommerce": f"People already interested in {niche} who compare options online before buying",
        "professional_services": f"People or organisations facing a specific {niche} problem and looking for trusted expert help",
        "local_business": f"People within the business's service area who are actively looking for {niche}",
        "agency": f"Business owners or marketing leads who need outside support with {niche}",
        "other": f"People most affected by the problem this {niche} business solves",
    }
    return {
        "audience": audience_by_model.get(business_model, audience_by_model["other"]),
        "needs": [
            "A clear, credible solution they can understand quickly",
            f"Confidence that the offer can help them achieve {primary_goal or 'a useful business or personal result'}",
            "Proof, examples, pricing or next steps that reduce uncertainty",
        ],
        "barriers": [
            "Uncertainty about whether the offer fits their situation",
            "Limited time, budget or attention",
            "A lack of trust, evidence or a clear reason to act now",
        ],
    }


def suggest_audience(brand_name, niche, business_model, primary_goal):
    """Return an AI audience hypothesis, falling back to a useful starter draft."""
    fallback = _starter_suggestion(niche, business_model, primary_goal)
    prompt = f"""
You are helping a small business create an initial social media strategy.

Brand: {brand_name or 'Not supplied'}
Industry or market: {niche}
Business model: {business_model}
Primary goal: {primary_goal or 'Not supplied'}

Create a cautious target-audience hypothesis. Do not claim research was performed and do not invent precise demographics, income, locations, statistics, or customer evidence. Focus on the likely buyer situation.

Return only JSON with this exact shape:
{{
  "audience": "One specific sentence describing who is most likely to buy",
  "needs": ["Three likely needs"],
  "barriers": ["Three likely obstacles, objections, or constraints"]
}}
"""
    try:
        response = generate_with_fallback(prompt)
        data = extract_json_from_llm(response.text)
        audience = str(data.get("audience", "")).strip()
        needs = [str(item).strip() for item in data.get("needs", []) if str(item).strip()][:3]
        barriers = [str(item).strip() for item in data.get("barriers", []) if str(item).strip()][:3]
        if not audience or not needs or not barriers:
            raise ValueError("Incomplete audience suggestion")
        return {"audience": audience, "needs": needs, "barriers": barriers, "source": "ai"}
    except Exception:
        return {**fallback, "source": "starter"}


def format_audience_suggestion(suggestion):
    needs = "; ".join(suggestion["needs"])
    barriers = "; ".join(suggestion["barriers"])
    return (
        f"Likely audience: {suggestion['audience']}\n\n"
        f"What they likely need: {needs}.\n\n"
        f"What may get in the way: {barriers}."
    )
