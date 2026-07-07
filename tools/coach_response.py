import os
import json
from google import genai
from google.genai import types
from tools.check_deadline import check_deadline
from memory.longterm import get_schedule, get_dailylogs
from datetime import datetime, timezone

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

def get_today_log(dailylogs: dict) -> dict | None:
    """Get today's most recent log entry."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logs = dailylogs.get("logs", [])
    today_logs = [l for l in logs if l.get("date", "").startswith(today)]
    return today_logs[-1] if today_logs else None

def get_coach_response(user_message: str, priority_id: str | None = None) -> dict:
    """
    Generates a coaching response grounded in:
    - Current schedule state
    - Deadline assessment if priority_id provided
    - Today's daily log (sleep, energy, mood)
    - User's message
    """
    schedule = get_schedule()
    dailylogs = get_dailylogs()
    today_log = get_today_log(dailylogs)

    context_parts = []

    if today_log:
        context_parts.append(f"""Today's logged state:
- Sleep quality: {today_log.get('sleep_quality', 'unknown')}/10
- Energy: {today_log.get('energy', 'unknown')}/10
- Mood: {today_log.get('mood', 'unknown')}/10
- Focus so far: {today_log.get('focus_so_far', 'unknown')}/10""")

    if priority_id:
        deadline_info = check_deadline(priority_id)
        if "error" not in deadline_info:
            context_parts.append(f"""Deadline assessment for '{deadline_info.get('priority_title')}':
- Hours remaining: {deadline_info.get('hours_remaining')}
- Tasks left: {deadline_info.get('tasks_left')}
- Time needed: {deadline_info.get('time_needed_hours')} hours
- Available time before deadline: {deadline_info.get('available_hours')} hours
- Fits: {deadline_info.get('fits')}
- Flexible options: {', '.join(deadline_info.get('flexible_options', []))}""")

    items = schedule.get("items", [])
    now = datetime.now(timezone.utc)
    upcoming = [
        i for i in items
        if i.get("confirmed") and i.get("start_time")
        and datetime.fromisoformat(i["start_time"]).replace(tzinfo=timezone.utc) > now
    ][:5]

    if upcoming:
        upcoming_str = "\n".join([
            f"- {i.get('title')} at {i.get('start_time', '')[:16]}"
            for i in upcoming
        ])
        context_parts.append(f"Upcoming schedule:\n{upcoming_str}")

    context = "\n\n".join(context_parts)

    system_prompt = """You are Coach — a pragmatic, operational schedule assistant.
You speak like a trusted parent: direct, honest, no fluff.

When someone is stuck or asks for help, you always:
1. Acknowledge what's real (their energy, their deadline pressure)
2. State the hard numbers (time left, work remaining)
3. Give exactly 2-3 concrete options — not vague suggestions
4. Ask them to confirm which option they want

You never moralize. You never say "you've got this".
You state facts and present choices. The user decides.

Always respond with valid JSON only, no markdown backticks, no other text:
{
  "acknowledgment": "one sentence acknowledging their situation",
  "time_left": "X hours Y minutes or N/A",
  "tasks_remaining": number or null,
  "situation": "one sentence summary of the real situation",
  "options": [
    {"label": "Option 1", "description": "concrete action"},
    {"label": "Option 2", "description": "concrete action"}
  ],
  "confirmation_prompt": "Which do you want to do?"
}"""

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1000
            ),
            contents=f"Context:\n{context}\n\nUser says: {user_message}"
        )

        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        return {
            "acknowledgment": parsed.get("acknowledgment", ""),
            "time_left": parsed.get("time_left", "N/A"),
            "tasks_remaining": parsed.get("tasks_remaining"),
            "situation": parsed.get("situation", ""),
            "options": parsed.get("options", []),
            "confirmation_prompt": parsed.get("confirmation_prompt", "What would you like to do?"),
            "raw_context": context if os.getenv("DEBUG") else None
        }

    except json.JSONDecodeError:
        return {
            "acknowledgment": "",
            "time_left": "N/A",
            "tasks_remaining": None,
            "situation": "Could not generate response",
            "options": [],
            "confirmation_prompt": "What would you like to do?"
        }
    except Exception as e:
        return {
            "acknowledgment": "",
            "time_left": "N/A",
            "tasks_remaining": None,
            "situation": str(e),
            "options": [],
            "confirmation_prompt": "What would you like to do?"
        }