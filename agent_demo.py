"""
Coach — Process Scheduler for Humans
A chiefOS Component | Kaggle 5-Day AI Agents Capstone

Terminal demo showing the agent harness:
- Instructions/rules (agent.py)
- Tools (skills)
- Orchestration (agent loop)
- Observability (logging)

Run: python agent_demo.py
"""

import os
import json
from datetime import datetime, timezone
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ─── Client ──────────────────────────────────────────────────────────────────

_client = None

def get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client

# ─── Tools (Skills) ──────────────────────────────────────────────────────────
# Each tool is a discrete skill the agent can call.
# The agent decides which tool to use based on the conversation.

def get_current_time() -> str:
    """Returns the current time and day."""
    now = datetime.now()
    return {
        "time": now.strftime("%I:%M %p"),
        "day": now.strftime("%A"),
        "date": now.strftime("%B %d, %Y"),
        "hour": now.hour
    }

def assess_capacity(commitments: list, energy_level: int = None) -> dict:
    """
    Calculates available capacity given a list of commitments.
    
    commitments: list of {title, start_hour, end_hour}
    energy_level: 1-10 if known from daily log
    
    Returns honest capacity assessment.
    """
    now = datetime.now()
    current_hour = now.hour
    end_of_day = 22  # 10pm default

    # Calculate committed minutes remaining today
    committed_minutes = 0
    upcoming = []

    for c in commitments:
        start = c.get("start_hour", 0)
        end = c.get("end_hour", 0)
        if end > current_hour:
            committed_minutes += max((end - max(start, current_hour)) * 60, 0)
            if start > current_hour:
                upcoming.append(c)

    total_minutes_left = max((end_of_day - current_hour) * 60, 0)
    free_minutes = max(total_minutes_left - committed_minutes, 0)

    # Adjust for energy if known
    effective_capacity = free_minutes
    if energy_level and energy_level <= 4:
        effective_capacity = free_minutes * 0.6  # low energy reduces effective capacity

    return {
        "free_minutes": round(free_minutes),
        "free_hours": round(free_minutes / 60, 1),
        "effective_hours": round(effective_capacity / 60, 1),
        "committed_minutes": round(committed_minutes),
        "upcoming_commitments": upcoming,
        "energy_adjusted": energy_level is not None and energy_level <= 4
    }

def log_recommendation(situation: str, recommendation: str, category: str):
    """
    Observability — logs every recommendation the agent makes.
    Append-only, never deletes.
    """
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "situation": situation,
        "recommendation": recommendation,
        "category": category
    }

    log_file = "demo_coach_log.json"
    logs = []

    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    logs.append(log_entry)

    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

# ─── Brain (Instructions) ─────────────────────────────────────────────────────

BRAIN = """You are Coach — a process scheduler for humans.

Your job is to answer one question: "What should I be doing right now?"

You always know:
- What time it is
- What commitments are coming up
- How much capacity is left
- What the person's energy state is

You make ONE recommendation per response. It falls into one of these categories:
- START: Begin something now
- PROTECT: Guard time or energy that's at risk
- DEFER: Move something to a better time
- RECOVER: Step away before the next thing
- PREPARE: Get ready for something coming up
- TRIAGE: Choose between competing demands
- PROTECT_CAPACITY: Flag overcommitment

FORMAT your response exactly like this:
CATEGORY: [one of the above]
SITUATION: [one sentence — what's actually happening right now]
RECOMMENDATION: [one specific action, grounded in the actual time and context]
NEXT ACTION: [the single smallest thing to do right now]

Rules:
- Never be vague. Name the specific time, the specific task, the specific person.
- Never moralize. State facts and move on.
- Never give more than one recommendation.
- Always ground the recommendation in what you actually know about the person's day."""

# ─── Agent Loop ──────────────────────────────────────────────────────────────

def parse_situation_with_gemini(user_input: str, time_context: dict) -> dict:
    """
    Uses Gemini to extract structured information from the user's description.
    Returns: {commitments, energy_level, concerns}
    """
    prompt = f"""Extract schedule information from this input.
Current time: {time_context['time']} on {time_context['day']}.

User said: "{user_input}"

Respond with valid JSON only:
{{
  "commitments": [
    {{"title": "string", "start_hour": number, "end_hour": number}}
  ],
  "energy_level": number or null,
  "hours_worked": number or null,
  "concerns": ["string"]
}}

For commitments, convert times to 24-hour integers (e.g. 2pm = 14, 9am = 9).
If no energy level is mentioned, return null.
If no commitments mentioned, return empty array."""

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL", "gemini-3.1-flash-lite"),
            config=types.GenerateContentConfig(
                max_output_tokens=500
            ),
            contents=prompt
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception:
        return {"commitments": [], "energy_level": None, "concerns": []}


def get_recommendation(user_input: str, time_context: dict, capacity: dict) -> str:
    """
    Core agent reasoning — calls Gemini with full context to generate recommendation.
    """
    upcoming_str = ""
    if capacity["upcoming_commitments"]:
        upcoming_str = "Upcoming: " + ", ".join([
            f"{c['title']} at {c['start_hour']}:00"
            for c in capacity["upcoming_commitments"]
        ])

    context = f"""Current time: {time_context['time']} on {time_context['day']}, {time_context['date']}

Capacity assessment:
- Free time remaining today: {capacity['free_hours']} hours
- Effective capacity (energy-adjusted): {capacity['effective_hours']} hours
- {upcoming_str}
- Energy adjusted: {capacity['energy_adjusted']}

Person said: "{user_input}" """

    try:
        response = get_client().models.generate_content(
            model=os.getenv("MODEL", "gemini-3.1-flash-lite"),
            config=types.GenerateContentConfig(
                system_instruction=BRAIN,
                max_output_tokens=300
            ),
            contents=context
        )
        return response.text.strip()
    except Exception as e:
        return f"Could not generate recommendation: {e}"


def run():
    """
    Main agent loop — the harness.
    
    1. Get context (time)
    2. Get user input
    3. Parse situation (tool call)
    4. Assess capacity (tool call)
    5. Generate recommendation (LLM call)
    6. Log recommendation (observability)
    7. Display result
    """
    print("\n" + "="*50)
    print("Coach — Process Scheduler for Humans")
    print("A chiefOS Component")
    print("="*50)

    # Step 1 — Get current time context (tool call)
    time_context = get_current_time()
    print(f"\nIt's {time_context['time']} on {time_context['day']}.\n")

    # Step 2 — Get user input
    print("Tell me what's on your plate right now.")
    print("(Include any meetings, deadlines, how long you've been working,")
    print(" how you're feeling, or anything else relevant.)\n")

    user_input = input("> ").strip()

    if not user_input:
        print("\nNothing to work with. Come back when you have something on your plate.")
        return

    print("\nAnalyzing your situation...\n")

    # Step 3 — Parse situation (tool call)
    situation = parse_situation_with_gemini(user_input, time_context)

    # Step 4 — Assess capacity (tool call)
    capacity = assess_capacity(
        commitments=situation.get("commitments", []),
        energy_level=situation.get("energy_level")
    )

    # Step 5 — Generate recommendation (LLM call with full context)
    recommendation = get_recommendation(user_input, time_context, capacity)

    # Step 6 — Log recommendation (observability)
    category = "UNKNOWN"
    for cat in ["START", "PROTECT", "DEFER", "RECOVER", "PREPARE", "TRIAGE", "PROTECT_CAPACITY"]:
        if cat in recommendation:
            category = cat
            break

    log_recommendation(user_input, recommendation, category)

    # Step 7 — Display result
    print("─"*50)
    print(recommendation)
    print("─"*50)
    print(f"\n[Logged to demo_coach_log.json]\n")

    # Offer follow-up
    print("Need to break this down further? (yes/no)")
    followup = input("> ").strip().lower()

    if followup in ["yes", "y"]:
        print("\nWhat specifically are you stuck on?\n")
        stuck = input("> ").strip()

        if stuck:
            print("\nBreaking it down...\n")

            breakdown_prompt = f"""The person needs to break down a task.
They said: "{stuck}"
Current time: {time_context['time']}
They have {capacity['effective_hours']} effective hours left.

Give them the single smallest first step. Be specific.
Format:
FIRST STEP: [exactly what to do]
TIME NEEDED: [realistic minutes]
START WITH: [the very first physical action — open a file, pick up a phone, etc.]"""

            try:
                response = get_client().models.generate_content(
                    model=os.getenv("MODEL", "gemini-3.1-flash-lite"),
                    config=types.GenerateContentConfig(
                        max_output_tokens=200
                    ),
                    contents=breakdown_prompt
                )
                print("─"*50)
                print(response.text.strip())
                print("─"*50)
            except Exception as e:
                print(f"Could not break down: {e}")


if __name__ == "__main__":
    run()
