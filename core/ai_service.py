import os
import json
from google import genai
from dotenv import load_dotenv

load_dotenv()


def get_gemini_client():
    """Initializes and returns the Gemini client using the key from .env"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in your .env file.")
    return genai.Client(api_key=api_key)


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

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    clean_text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean_text)


def generate_monthly_report(brand_name, brand_niche, month_year, metrics_data):
    """
    PILLAR 2: THE REPORTING ENGINE (Arike's Framework)
    Turns monthly analytics into an executive-ready client report:
    1. Executive Summary
    2. 3 Key Insights (The 'Why')
    3. Next Month Strategy (Double Down, Test, Stop)
    """
    client = get_gemini_client()

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

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
    )

    clean_text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(clean_text)
