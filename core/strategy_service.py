"""A usable strategy baseline that does not require an external AI service."""

import re
from datetime import timedelta

from django.utils import timezone


def _platforms(brand, requested):
    selected = [part.strip() for part in (requested or "").split(",") if part.strip()]
    if selected:
        return selected[:2]
    model = (brand.business_model or "").lower()
    if "b2b" in model or "professional" in model or "agency" in model:
        return ["LinkedIn"]
    if "local" in model:
        return ["Instagram"]
    return ["Instagram"]


def build_foundation(brand, platforms):
    inputs = brand.strategy_inputs or {}
    stage = inputs.get("brand_stage") or "unknown"
    audit_notes = (inputs.get("audit_notes") or "").strip()
    metric = inputs.get("goal_metric") or "the result that matters most to your business"
    baseline = str(inputs.get("baseline") or "").strip()
    target = str(inputs.get("target") or "").strip()
    deadline = str(inputs.get("deadline") or "").strip()
    metric_text = str(metric).strip().rstrip(".")
    metric_is_goal_sentence = len(metric_text.split()) >= 5 or any(
        metric_text.lower().startswith(prefix) for prefix in ("sell ", "get ", "generate ", "increase ", "reach ")
    )
    if baseline and target and deadline:
        goal = f"Increase {metric} from {baseline} to {target} by {deadline}."
    elif target and deadline and metric_is_goal_sentence:
        metric_text = re.sub(r"\s+in (?:the )?next \d+ months?\b", "", metric_text, flags=re.IGNORECASE).strip()
        goal = f"{metric_text[0].upper() + metric_text[1:]} by {deadline}."
    elif target and deadline:
        goal = f"Reach {target} {metric_text} by {deadline}."
    else:
        goal = f"Measure {metric} for 30 days, then set a realistic 90-day target."
    today = timezone.localdate()
    if stage == "new":
        audit = "This is a new brand with no posts to review. Use the first 30 days to establish a starting point."
    elif audit_notes:
        audit = audit_notes
    elif stage == "active":
        audit = "The brand is already posting, but past results were not provided. Review recent posts before finalising this strategy."
    else:
        audit = "Posting history was not provided. Confirm whether the brand has existing posts before finalising this strategy."
    assumptions = ["Confirm that the chosen platform is used by the people you want to reach."]
    if not inputs.get("audience_evidence"):
        assumptions.append("Customer questions and needs have not been confirmed yet.")
    if not audit_notes and stage != "new":
        assumptions.append("No past post results were supplied to guide the content mix.")
    if inputs.get("competitor_notes"):
        assumptions.append("The similar brands listed have not been analysed yet; their activity and results need checking.")
    return {
        "goal": goal,
        "goal_metric": metric,
        "baseline": baseline,
        "target": target,
        "deadline": deadline,
        "checkins": [str(today + timedelta(days=days)) for days in (30, 60, 90)],
        "audience": brand.target_audience,
        "audience_evidence": inputs.get("audience_evidence") or "Customer feedback has not been supplied yet.",
        "brand_stage": stage,
        "audit": audit,
        "competitors": f"Accounts to review: {inputs['competitor_notes']}" if inputs.get("competitor_notes") else "No similar brands were added. Add a few names or links when available.",
        "keywords": [word.strip() for word in (inputs.get("customer_keywords") or "").split(",") if word.strip()],
        "budget": inputs.get("budget") or "0",
        "verified_business_details": {
            "service_area": inputs.get("service_area") or "Needs confirmation",
            "offer_details": inputs.get("offer_details") or "Needs confirmation",
            "price_range": inputs.get("price_range") or "Needs confirmation",
            "differentiators": inputs.get("differentiators") or "Needs confirmation",
            "proof_available": inputs.get("proof_available") or "No usable proof supplied yet",
        },
        "platforms": platforms,
        "assumptions": assumptions,
    }


def generate_starter_strategy(brand, requested_platforms="", requested_weekly_posts=None):
    platforms = _platforms(brand, requested_platforms)
    foundation = build_foundation(brand, platforms)
    capacity = max(1, brand.weekly_posts_capacity)
    weekly_posts = min(requested_weekly_posts or capacity, capacity)
    post_word = "post" if weekly_posts == 1 else "posts"
    cadence_basis = (
        f"The brand owner said they can sustain up to {capacity} {('post' if capacity == 1 else 'posts')} "
        f"per week. This plan uses {weekly_posts} {post_word} and will not exceed that limit."
    )
    foundation["cadence_basis"] = cadence_basis
    foundation["weekly_posts"] = weekly_posts
    primary = platforms[0]
    keywords = foundation["keywords"]
    customer_phrase = keywords[0] if keywords else "the problem your customers describe most often"
    first_source = foundation["audience_evidence"] if brand.strategy_inputs.get("audience_evidence") else "a question you heard from a real customer"
    pillars = [
        ("Customer questions", "Answer real questions and objections before customers buy.", 35),
        ("Practical help", "Show a useful step or example related to your offer.", 30),
        ("Proof and process", "Show how the product or service works; use real customer proof only with permission.", 20),
        ("Conversation and offer", "Invite a useful response and clearly explain the next step to buy or enquire.", 15),
    ]
    content_pillars = [
        {"name": name, "description": description, "percentage_of_content": f"{weight}%",
         "commercial_rationale": f"Connects a customer need to your goal: {foundation['goal_metric']}.",
         "example_topics": [customer_phrase] if index == 0 else []}
        for index, (name, description, weight) in enumerate(pillars)
    ]
    formats = ["Phone video", "Text post", "Photo with caption"]
    ideas = [
        ("Customer questions", f"What do customers mean when they ask about {customer_phrase}?", f"Use {first_source} as the source; answer one real question in plain language."),
        ("Practical help", f"A simple way to handle {customer_phrase}", "Demonstrate one useful step with a real example."),
        ("Proof and process", "What happens when someone works with us?", "Walk through the actual process without invented results."),
        ("Conversation and offer", "Is this a problem you are dealing with?", "Explain who the offer helps and invite a relevant enquiry."),
    ]
    content_ideas = [
        {"pillar": pillar, "platform": primary, "funnel_stage": "Awareness" if index < 2 else "Consideration",
         "format": formats[index % len(formats)], "hook": hook, "concept": concept,
         "claim_classification": "evidence_required" if index == 2 else "educational",
         "evidence_note": "Use only a real customer example with permission." if index == 2 else "Check against your own offer and customer language."}
        for index, (pillar, hook, concept) in enumerate(ideas)
    ]
    if foundation["brand_stage"] == "new":
        first_action = "Finish the profile, introduce the offer, and publish one answer to a question a potential customer might ask."
    elif foundation["brand_stage"] == "active":
        first_action = "Review recent posts and publish an updated answer to a customer question."
    else:
        first_action = "Confirm whether the account has past posts. If it does, review them; if not, introduce the offer and publish a useful answer."
    tactics = [
        {"week": 1, "action": f"{first_action} Publish {weekly_posts} {post_word}: an introduction, one useful answer, and a clear offer post where capacity allows.", "cost": "Give every post one next step and record enquiries."},
        {"week": 2, "action": f"Publish {weekly_posts} {post_word} using real customer questions and one verified product or service example.", "cost": "Reuse one source across formats without inventing proof."},
        {"week": 3, "action": f"Publish {weekly_posts} {post_word} that explain the offer, address an objection, and invite a qualified enquiry.", "cost": "Use only confirmed prices, processes and results."},
        {"week": 4, "action": f"Publish {weekly_posts} {post_word}, then compare topics, formats, clicks and qualified enquiries across the month.", "cost": "Keep the strongest topic and change one weak element next month."},
    ]
    foundation["tactics"] = tactics
    return {
        "strategy_foundation": foundation,
        "executive_summary": f"This strategy focuses on {primary} and a sustainable cadence of {weekly_posts} {post_word} per week. Customer questions and real brand examples will build trust, introduce the offer, and support {foundation['goal_metric']}. Results will be reviewed after 30 days and used to refine the next phase.",
        "audience_icp_dossier": {
            "evidence_basis": foundation["audience_evidence"],
            "target_audience": brand.target_audience,
            "personas": [
                {"name": "Primary buyer", "evidence_status": "Hypothesis", "description": brand.target_audience, "goal": "Solve the main problem described in the brand brief", "barrier": "Needs confirmation through customer conversations", "content_need": "Clear explanations, relevant examples and a direct next step"},
                {"name": "Careful evaluator", "evidence_status": "Hypothesis", "description": "A potential customer comparing options before committing", "goal": "Reduce risk and make a confident choice", "barrier": "Unanswered questions, unclear proof or price uncertainty", "content_need": "Comparisons, process explanations and verified proof"},
                {"name": "Ready-to-act prospect", "evidence_status": "Hypothesis", "description": "A suitable prospect who already understands the problem", "goal": "Confirm fit and take the next step", "barrier": "Friction in contacting, booking or buying", "content_need": "Offer details, availability and one clear call to action"},
            ],
        },
        "content_pillars": content_pillars,
        "platform_playbook": [{"platform": platform, "priority": "Primary" if index == 0 else "Secondary",
                               "rationale": "A starting choice for this kind of business. Check whether your customers use it and respond to your posts."}
                              for index, platform in enumerate(platforms)],
        "content_mix": {"teaching": "40%", "conversation": "25%", "proof_and_process": "20%", "promotion": "15%"},
        "posting_schedule": [{"platform": primary, "frequency": f"{weekly_posts} per week",
                              "rationale": cadence_basis}],
        "content_ideas": content_ideas,
        "kpis": [{"primary_kpi": foundation["goal_metric"], "monthly_targets": foundation["goal"],
                  "secondary_kpis": ["Posts published", "Relevant replies or enquiries"]}],
        "cta_strategy": [{"awareness_stage": "All", "goal": "Invite a relevant next step",
                          "cta_examples": [f"Ask a question or visit {brand.conversion_url or 'our contact page'}."],
                          "platforms": platforms}],
    }
