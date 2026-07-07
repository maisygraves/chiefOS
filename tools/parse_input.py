import os
import json
from google import genai
from google.genai import types
from datetime import datetime

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

def detect_intent(text: str) -> dict:
    """
    Determines if input needs:
    - onboarding (set up my schedule, start over, configure)
    - guided intake (recurring items, needs, vague items)
    - direct parsing (specific one-off items with date/time)
    """
    system_prompt = """You are an intent classifier for a schedule agent.
Determine the mode for this input.

Respond with valid JSON only, no markdown:
{
  "mode": "onboarding" or "guided" or "direct",
  "category": "need" or "priority" or "sporadic",
  "hint": "one sentence describing what was detected"
}

Use "onboarding" when:
- Person wants to set up their schedule from scratch
- Input includes: "set up", "onboard", "configure", "start over", "build my schedule"

Use "guided" when:
- The item is recurring ("every night", "daily", "every morning")
- The item is a human need (sleep, meals, exercise, hygiene)
- The item is vague and needs clarification ("I want to add exercise")

Use "direct" when:
- Specific date and time present ("dentist friday 2pm")
- Clearly one-off with all information present"""

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=200
            ),
            contents=f"Classify this input: {text}"
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"mode": "direct", "category": "sporadic", "hint": text}

def parse_input_to_candidate(text: str) -> dict:
    """
    Calls Gemini to parse natural language into a ScheduleItem candidate.
    Returns structured candidate for user confirmation before placing.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    day_of_week = datetime.now().strftime("%A")

    system_prompt = """You are a schedule parser. Convert natural language 
into a structured schedule item. Always respond with valid JSON only,
no other text, no markdown backticks.

Respond with this exact structure:
{
  "title": "string",
  "type": "need|responsibility|recurring_priority|oneoff_priority|task",
  "start_time": "ISO8601 datetime",
  "end_time": "ISO8601 datetime",
  "has_deadline": false,
  "deadline": null,
  "is_flexible": true,
  "notes": "string or null"
}"""

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1000
            ),
            contents=f"Today is {day_of_week} {today}. Parse this into a schedule item: {text}"
        )

        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        candidate = json.loads(raw)
        return {
            "candidate": candidate,
            "original_text": text,
            "needs_confirmation": True
        }

    except json.JSONDecodeError:
        return {
            "candidate": None,
            "original_text": text,
            "needs_confirmation": True,
            "error": "Could not parse input — please try rephrasing"
        }
    except Exception as e:
        return {
            "candidate": None,
            "original_text": text,
            "needs_confirmation": True,
            "error": str(e)
        }