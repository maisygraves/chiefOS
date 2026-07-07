import os
import json
import uuid
from google import genai
from google.genai import types
from datetime import datetime, timezone

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

def breakdown_priority(priority: dict) -> list[dict]:
    """
    Takes a Priority, calls Gemini to break it into concrete Tasks
    with time estimates and quality targets.
    """
    title = priority.get("title", "Unnamed priority")
    deadline = priority.get("deadline")
    priority_type = priority.get("type", "oneoff_priority")
    notes = priority.get("notes", "")

    deadline_str = f"Deadline: {deadline}" if deadline else "No hard deadline"

    system_prompt = """You are Coach — a pragmatic schedule assistant.
Break down priorities into concrete, actionable tasks.
Each task should be completable in one focused sitting.
Be specific and realistic about time estimates.

Respond with valid JSON only, no markdown backticks, no other text:
{
  "tasks": [
    {
      "title": "specific action",
      "estimated_minutes": number,
      "quality_target": "what done looks like",
      "order": number
    }
  ]
}

Rules:
- 2-7 tasks maximum
- estimated_minutes between 15 and 120
- quality_target is one concrete sentence describing what done looks like
- tasks should be in logical order"""

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1000
            ),
            contents=f"""Break down this priority into tasks:

Title: {title}
Type: {priority_type}
{deadline_str}
Notes: {notes if notes else 'None'}"""
        )

        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)
        tasks = parsed.get("tasks", [])

        return [
            {
                "id": str(uuid.uuid4()),
                "title": t.get("title"),
                "type": "task",
                "parent_priority_id": priority.get("id"),
                "estimated_minutes": t.get("estimated_minutes", 30),
                "quality_target": t.get("quality_target", "Completed"),
                "order": t.get("order", i + 1),
                "completed": False,
                "confirmed": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            for i, t in enumerate(tasks)
        ]

    except (json.JSONDecodeError, Exception):
        return [{
            "id": str(uuid.uuid4()),
            "title": f"Work on {title}",
            "type": "task",
            "parent_priority_id": priority.get("id"),
            "estimated_minutes": 60,
            "quality_target": "Meaningful progress made",
            "order": 1,
            "completed": False,
            "confirmed": False,
            "created_at": datetime.now(timezone.utc).isoformat()
        }]