import os
import json
import uuid
from google import genai
from google.genai import types
from datetime import datetime, timezone, timedelta
from memory.longterm import get_schedule, save_schedule

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

# ─── Onboarding steps ────────────────────────────────────────────────────────
# Each step maps to a section of the profile
# The agent works through these in order during first-time setup

ONBOARDING_STEPS = [
    {
        "step": "sleep",
        "label": "Sleep",
        "questions": [
            {"field": "sleep_start", "question": "What time do you usually go to sleep?"},
            {"field": "sleep_end",   "question": "What time do you usually wake up?"},
            {"field": "wind_down",   "question": "How long do you need to wind down before sleep? (e.g. 30 mins, or skip)"},
            {"field": "wake_buffer", "question": "How long do you need after waking before you're ready to start your day? (e.g. 30 mins, or skip)"},
        ]
    },
    {
        "step": "needs",
        "label": "Daily needs",
        "questions": [
            {"field": "needs_list", "question": "What are your daily non-negotiables? Things that happen every day — meals, exercise, hygiene. List them with rough durations. (e.g. breakfast 30 mins, gym 1 hour, shower 20 mins)"},
        ]
    },
    {
        "step": "responsibilities",
        "label": "Committed time",
        "questions": [
            {"field": "work_hours",       "question": "What are your work hours or main committed blocks? (e.g. work Mon-Fri 9am-5pm, or school Tue/Thu 10am-2pm)"},
            {"field": "other_commitments","question": "Any other recurring commitments? (e.g. weekly team meeting Tues 10am, therapy every other Thursday). Type 'none' to skip."},
        ]
    },
    {
        "step": "priorities",
        "label": "Priorities",
        "questions": [
            {"field": "priorities_list", "question": "What are you trying to make progress on right now? List your top 3 priorities with how much time per week you want to give each. (e.g. learn Python 5hrs/week, side project 3hrs/week, reading 1hr/day)"},
        ]
    },
    {
        "step": "buffer",
        "label": "Buffer and transitions",
        "questions": [
            {"field": "buffer_minutes", "question": "How much buffer do you want between tasks? (e.g. 10 mins, 15 mins, 30 mins)"},
        ]
    }
]

# ─── Single item questions ────────────────────────────────────────────────────

ITEM_QUESTIONS = {
    "need": [
        {"field": "title",              "question": "What is this need? (e.g. Sleep, Lunch, Exercise)"},
        {"field": "start_time",         "question": "What time does it start?"},
        {"field": "end_time",           "question": "What time does it end?"},
        {"field": "recurrence_pattern", "question": "How often? (daily, weekdays, weekends, or weekly)"},
    ],
    "priority": [
        {"field": "title",              "question": "What is this priority?"},
        {"field": "start_time",         "question": "What time does it start?"},
        {"field": "end_time",           "question": "What time does it end?"},
        {"field": "recurrence_pattern", "question": "How often? (daily, weekdays, weekends, weekly, or one-off)"},
        {"field": "has_deadline",       "question": "Does this have a deadline? (yes/no)"},
        {"field": "deadline",           "question": "When is the deadline?", "condition": "has_deadline"},
    ],
    "sporadic": [
        {"field": "title",      "question": "What is this?"},
        {"field": "start_time", "question": "What date and time does it start?"},
        {"field": "end_time",   "question": "What time does it end?"},
        {"field": "is_flexible","question": "Is the time flexible? (yes/no)"},
    ]
}

# ─── Time parsing ─────────────────────────────────────────────────────────────

def parse_time_string(answer: str) -> str:
    """Uses Gemini to convert natural language time to ISO8601."""
    today = datetime.now().strftime("%Y-%m-%d")
    day_of_week = datetime.now().strftime("%A")
    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=f"Convert to ISO8601 datetime. Today is {day_of_week} {today}. Respond with only the ISO8601 string, nothing else.",
                max_output_tokens=50
            ),
            contents=answer
        )
        return response.text.strip()
    except Exception:
        return answer

def parse_answer(field: str, answer: str, collected: dict) -> any:
    """Parses a user answer into the correct type for a given field."""
    if field in ["has_deadline", "is_flexible"]:
        return answer.lower().strip() in ["yes", "y", "true", "1"]

    if field in ["start_time", "end_time", "deadline", "sleep_start", "sleep_end"]:
        return parse_time_string(answer)

    if field == "buffer_minutes":
        # Extract number from answer
        import re
        numbers = re.findall(r'\d+', answer)
        return int(numbers[0]) if numbers else 10

    if field == "wind_down" or field == "wake_buffer":
        if answer.lower().strip() in ["skip", "none", "no", "0"]:
            return 0
        import re
        numbers = re.findall(r'\d+', answer)
        return int(numbers[0]) if numbers else 0

    if field == "recurrence_pattern":
        a = answer.lower().strip()
        if any(w in a for w in ["every day", "daily", "each day"]):
            return "daily"
        if any(w in a for w in ["weekday", "mon-fri", "work day"]):
            return "weekdays"
        if any(w in a for w in ["weekend", "sat", "sun"]):
            return "weekends"
        if any(w in a for w in ["week", "weekly"]):
            return "weekly"
        if any(w in a for w in ["once", "one time", "one-off", "just this"]):
            return None
        return answer

    return answer

# ─── Profile saving ───────────────────────────────────────────────────────────

def save_profile_field(field: str, value: any):
    """Saves a single profile field to schedule.json immediately."""
    schedule = get_schedule()
    if "profile" not in schedule:
        schedule["profile"] = {}
    schedule["profile"][field] = value
    save_schedule(schedule)

def get_current_schedule_summary() -> dict:
    """Returns the current schedule state for display at start of onboarding."""
    schedule = get_schedule()
    items = schedule.get("items", [])
    profile = schedule.get("profile", {})

    return {
        "has_profile": bool(profile),
        "item_count": len(items),
        "items": items[:5],  # first 5 for preview
        "profile": profile,
        "window_start": schedule.get("window_start"),
        "window_end": schedule.get("window_end")
    }

# ─── Onboarding flow ──────────────────────────────────────────────────────────

def get_next_onboarding_question(collected: dict) -> dict | None:
    """
    Returns the next unanswered onboarding question across all steps.
    Returns None when onboarding is complete.
    """
    for step in ONBOARDING_STEPS:
        for q in step["questions"]:
            if q["field"] not in collected:
                return {**q, "step": step["step"], "step_label": step["label"]}
    return None

def run_onboarding_step(
    collected: dict,
    latest_answer: str | None = None,
    last_field: str | None = None
) -> dict:
    """
    One step of the onboarding conversation.
    Saves each answer to profile immediately.
    Returns next question or completion summary.
    """
    # Parse and save latest answer
    if latest_answer and last_field:
        parsed = parse_answer(last_field, latest_answer, collected)
        collected[last_field] = parsed
        save_profile_field(last_field, parsed)

    # Get next question
    next_q = get_next_onboarding_question(collected)

    if next_q:
        return {
            "status": "asking",
            "mode": "onboarding",
            "step": next_q["step"],
            "step_label": next_q["step_label"],
            "question": next_q["question"],
            "field": next_q["field"],
            "collected": collected,
            "progress": f"{len(collected)} of {sum(len(s['questions']) for s in ONBOARDING_STEPS)} questions"
        }

    # Onboarding complete — generate schedule from profile
    schedule = get_schedule()
    profile = schedule.get("profile", {})

    result = generate_schedule_from_profile(profile)

    return {
        "status": "complete",
        "mode": "onboarding",
        "collected": collected,
        "profile": profile,
        "placed": result.get("placed", []),
        "failed": result.get("failed", []),
        "free_time": result.get("free_time", {}),
        "message": result.get("message", "Schedule built."),
        "needs_confirmation": False  # already placed — no confirmation needed
    }

# ─── Single item flow ─────────────────────────────────────────────────────────

def get_next_item_question(category: str, collected: dict) -> dict | None:
    """Returns next unanswered question for a single item intake."""
    questions = ITEM_QUESTIONS.get(category, ITEM_QUESTIONS["sporadic"])
    for q in questions:
        if "condition" in q:
            condition_value = collected.get(q["condition"])
            if not condition_value or condition_value in [False, "no", "No"]:
                continue
        if q["field"] not in collected:
            return q
    return None

def build_candidate(category: str, collected: dict) -> dict:
    """Builds a ScheduleItem candidate from collected answers."""
    type_map = {
        "need": "need",
        "priority": "recurring_priority" if collected.get("recurrence_pattern") else "oneoff_priority",
        "sporadic": "oneoff_priority"
    }
    return {
        "id": str(uuid.uuid4()),
        "title": collected.get("title", "Untitled"),
        "type": type_map.get(category, "oneoff_priority"),
        "start_time": collected.get("start_time"),
        "end_time": collected.get("end_time"),
        "has_deadline": collected.get("has_deadline", False),
        "deadline": collected.get("deadline"),
        "is_flexible": collected.get("is_flexible", True),
        "recurring": bool(collected.get("recurrence_pattern")),
        "recurrence_pattern": collected.get("recurrence_pattern"),
        "notes": collected.get("notes")
    }

def run_intake_step(
    category: str,
    collected: dict,
    latest_answer: str | None = None,
    last_field: str | None = None
) -> dict:
    """
    One step of the single item intake conversation.
    Returns next question or completed candidate.
    """
    if latest_answer and last_field:
        parsed = parse_answer(last_field, latest_answer, collected)
        collected[last_field] = parsed

    next_q = get_next_item_question(category, collected)

    if next_q:
        return {
            "status": "asking",
            "mode": "item",
            "question": next_q["question"],
            "field": next_q["field"],
            "collected": collected
        }

    candidate = build_candidate(category, collected)
    return {
        "status": "complete",
        "mode": "item",
        "candidate": candidate,
        "collected": collected,
        "needs_confirmation": True
    }

# ─── Schedule generation from profile ────────────────────────────────────────

def parse_profile_time(time_str: str, date_str: str) -> str:
    """
    Combines a time string (e.g. "23:00") with a date string (e.g. "2026-07-01")
    into a full ISO8601 datetime.
    """
    try:
        # Handle ISO8601 times that already have a date
        if 'T' in str(time_str):
            dt = datetime.fromisoformat(str(time_str))
            # Replace date with the target date
            target = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.replace(
                year=target.year,
                month=target.month,
                day=target.day,
                tzinfo=timezone.utc
            ).isoformat()
        # Handle HH:MM format
        if ':' in str(time_str):
            hour, minute = str(time_str).split(':')[:2]
            target = datetime.strptime(date_str, "%Y-%m-%d")
            return target.replace(
                hour=int(hour),
                minute=int(minute),
                second=0,
                microsecond=0,
                tzinfo=timezone.utc
            ).isoformat()
    except Exception:
        pass
    return time_str


def parse_needs_with_gemini(needs_text: str) -> list[dict]:
    """
    Uses Gemini to parse free-text needs into structured items.
    e.g. "breakfast 30 mins, gym 1 hour, shower 20 mins"
    Returns list of {title, duration_minutes, time_of_day}
    """
    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction="""Parse this list of daily needs into structured JSON.
Respond with valid JSON only, no markdown:
{
  "needs": [
    {
      "title": "string",
      "duration_minutes": number,
      "time_of_day": "morning" or "midday" or "evening" or "flexible"
    }
  ]
}""",
                max_output_tokens=500
            ),
            contents=needs_text
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        return parsed.get("needs", [])
    except Exception:
        return []


def parse_commitments_with_gemini(commitments_text: str) -> list[dict]:
    """
    Uses Gemini to parse free-text commitments into structured items.
    e.g. "work Mon-Fri 9am-5pm, weekly team meeting Tues 10am"
    Returns list of {title, start_time, end_time, recurrence_pattern, days}
    """
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL"),
            config=types.GenerateContentConfig(
                system_instruction=f"""Parse commitments into structured JSON. Today is {today}.
Respond with valid JSON only, no markdown:
{{
  "commitments": [
    {{
      "title": "string",
      "start_time": "HH:MM",
      "end_time": "HH:MM",
      "recurrence_pattern": "daily" or "weekdays" or "weekends" or "weekly",
      "days": ["monday", "tuesday"] or null
    }}
  ]
}}""",
                max_output_tokens=800
            ),
            contents=commitments_text
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        return parsed.get("commitments", [])
    except Exception:
        return []


def calculate_free_time(schedule: dict) -> dict:
    """
    Calculates free time per day in the 14-day window.
    Returns dict of {date: free_minutes} and a weekly summary.
    """
    items = schedule.get("items", [])
    window_start_str = schedule.get("window_start")
    window_end_str = schedule.get("window_end")

    try:
        window_start = datetime.fromisoformat(window_start_str).replace(tzinfo=timezone.utc)
        window_end = datetime.fromisoformat(window_end_str).replace(tzinfo=timezone.utc)
    except Exception:
        now = datetime.now(timezone.utc)
        window_start = now
        window_end = now + timedelta(days=14)

    # 16 waking hours = 960 minutes as baseline
    # (sleep is already accounted for as a need)
    MINUTES_PER_DAY = 960

    free_by_day = {}
    current = window_start

    while current <= window_end:
        date_str = current.strftime("%Y-%m-%d")
        committed_minutes = 0

        for item in items:
            try:
                item_start = datetime.fromisoformat(item["start_time"])
                item_end = datetime.fromisoformat(item["end_time"])
                if item_start.tzinfo is None:
                    item_start = item_start.replace(tzinfo=timezone.utc)
                if item_end.tzinfo is None:
                    item_end = item_end.replace(tzinfo=timezone.utc)

                if item_start.strftime("%Y-%m-%d") == date_str:
                    duration = (item_end - item_start).total_seconds() / 60
                    committed_minutes += max(duration, 0)
            except Exception:
                continue

        free_minutes = max(MINUTES_PER_DAY - committed_minutes, 0)
        free_by_day[date_str] = {
            "free_minutes": round(free_minutes),
            "free_hours": round(free_minutes / 60, 1),
            "committed_minutes": round(committed_minutes),
            "day_name": current.strftime("%A")
        }

        current += timedelta(days=1)

    # Weekly summary
    total_free = sum(d["free_minutes"] for d in free_by_day.values())
    avg_free = total_free / len(free_by_day) if free_by_day else 0

    return {
        "by_day": free_by_day,
        "total_free_hours": round(total_free / 60, 1),
        "avg_free_hours_per_day": round(avg_free / 60, 1)
    }


def generate_schedule_from_profile(profile: dict) -> dict:
    """
    Converts onboarding profile answers into schedule items.
    Called at end of onboarding — generates the first 14-day schedule.

    Takes the profile dict and:
    1. Creates sleep as a recurring need
    2. Creates daily needs as recurring items
    3. Creates committed time as recurring responsibilities
    4. Places everything in the 14-day window
    5. Calculates and returns free time summary
    """
    from tools.place_item import place_confirmed_item

    schedule = get_schedule()
    now = datetime.now(timezone.utc)
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(days=14)

    # Update window
    schedule["window_start"] = window_start.isoformat()
    schedule["window_end"] = window_end.isoformat()
    save_schedule(schedule)

    placed = []
    failed = []

    # ── 1. Sleep ──────────────────────────────────────────────────────────────
    sleep_start = profile.get("sleep_start")
    sleep_end = profile.get("sleep_end")

    if sleep_start and sleep_end:
        sleep_item = {
            "id": str(uuid.uuid4()),
            "title": "Sleep",
            "type": "need",
            "start_time": parse_profile_time(sleep_start, window_start.strftime("%Y-%m-%d")),
            "end_time": parse_profile_time(sleep_end, window_start.strftime("%Y-%m-%d")),
            "has_deadline": False,
            "deadline": None,
            "is_flexible": False,
            "recurring": True,
            "recurrence_pattern": "daily",
            "notes": None
        }
        result = place_confirmed_item(sleep_item)
        if result["success"]:
            placed.append(f"Sleep ({result.get('placed_count', 1)} instances)")
        else:
            failed.append(f"Sleep: {result.get('flag')}")

    # ── 2. Daily needs ────────────────────────────────────────────────────────
    needs_text = profile.get("needs_list", "")
    if needs_text and needs_text.lower() not in ["none", "skip", ""]:
        needs = parse_needs_with_gemini(needs_text)

        # Default time slots by time of day
        time_slots = {
            "morning":  ("07:00", "07:30"),
            "midday":   ("12:00", "12:30"),
            "evening":  ("18:00", "18:30"),
            "flexible": ("09:00", "09:30"),
        }

        for need in needs:
            tod = need.get("time_of_day", "flexible")
            default_start, default_end = time_slots.get(tod, ("09:00", "09:30"))
            duration = need.get("duration_minutes", 30)

            # Calculate end time from duration
            start_hour, start_min = map(int, default_start.split(":"))
            total_mins = start_hour * 60 + start_min + duration
            end_hour = (total_mins // 60) % 24
            end_min = total_mins % 60
            end_time_str = f"{end_hour:02d}:{end_min:02d}"

            need_item = {
                "id": str(uuid.uuid4()),
                "title": need["title"],
                "type": "need",
                "start_time": parse_profile_time(default_start, window_start.strftime("%Y-%m-%d")),
                "end_time": parse_profile_time(end_time_str, window_start.strftime("%Y-%m-%d")),
                "has_deadline": False,
                "deadline": None,
                "is_flexible": False,
                "recurring": True,
                "recurrence_pattern": "daily",
                "notes": None
            }
            result = place_confirmed_item(need_item)
            if result["success"]:
                placed.append(f"{need['title']} ({result.get('placed_count', 1)} instances)")
            else:
                failed.append(f"{need['title']}: {result.get('flag')}")

    # ── 3. Committed time ─────────────────────────────────────────────────────
    work_hours = profile.get("work_hours", "")
    other_commitments = profile.get("other_commitments", "")

    all_commitments_text = " ".join(filter(None, [work_hours, other_commitments]))
    if all_commitments_text and all_commitments_text.lower() not in ["none", "skip"]:
        commitments = parse_commitments_with_gemini(all_commitments_text)

        for commitment in commitments:
            start_str = commitment.get("start_time", "09:00")
            end_str = commitment.get("end_time", "17:00")

            commitment_item = {
                "id": str(uuid.uuid4()),
                "title": commitment["title"],
                "type": "responsibility",
                "start_time": parse_profile_time(start_str, window_start.strftime("%Y-%m-%d")),
                "end_time": parse_profile_time(end_str, window_start.strftime("%Y-%m-%d")),
                "has_deadline": False,
                "deadline": None,
                "is_flexible": False,
                "recurring": True,
                "recurrence_pattern": commitment.get("recurrence_pattern", "weekdays"),
                "notes": None
            }
            result = place_confirmed_item(commitment_item)
            if result["success"]:
                placed.append(f"{commitment['title']} ({result.get('placed_count', 1)} instances)")
            else:
                failed.append(f"{commitment['title']}: {result.get('flag')}")

    # ── 4. Calculate free time ────────────────────────────────────────────────
    updated_schedule = get_schedule()
    free_time = calculate_free_time(updated_schedule)

    return {
        "success": True,
        "placed": placed,
        "failed": failed,
        "free_time": free_time,
        "message": f"Schedule built. You have an average of {free_time['avg_free_hours_per_day']} free hours per day."
    }