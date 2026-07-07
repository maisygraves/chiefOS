from datetime import datetime, timezone
from memory.longterm import get_schedule

def parse_time(t: str) -> datetime:
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise ValueError(f"Cannot parse time: {t}")

def get_available_blocks(schedule_items: list, min_minutes: int = 30) -> list:
    """Find free blocks of at least min_minutes in the 14-day window."""
    now = datetime.now(timezone.utc)
    confirmed = [
        i for i in schedule_items
        if i.get("confirmed") and i.get("start_time") and i.get("end_time")
    ]
    confirmed.sort(key=lambda x: parse_time(x["start_time"]))

    free_blocks = []
    cursor = now

    for item in confirmed:
        try:
            item_start = parse_time(item["start_time"])
            item_end = parse_time(item["end_time"])
        except ValueError:
            continue

        if item_start > cursor:
            gap_minutes = (item_start - cursor).total_seconds() / 60
            if gap_minutes >= min_minutes:
                free_blocks.append({
                    "start": cursor.isoformat(),
                    "end": item_start.isoformat(),
                    "minutes": round(gap_minutes)
                })
        if item_end > cursor:
            cursor = item_end

    return free_blocks

def check_deadline(priority_id: str) -> dict:
    """
    Given a priority ID, returns honest deadline assessment:
    hours remaining, tasks left, time needed, available blocks,
    whether it fits, and flexible options.
    """
    schedule = get_schedule()
    items = schedule.get("items", [])

    # Find the priority
    priority = next(
        (i for i in items if i.get("id") == priority_id),
        None
    )

    if not priority:
        return {"error": f"Priority {priority_id} not found"}

    if not priority.get("has_deadline") or not priority.get("deadline"):
        return {"error": f"Priority {priority_id} has no deadline"}

    try:
        deadline = parse_time(priority["deadline"])
    except ValueError:
        return {"error": "Invalid deadline format"}

    now = datetime.now(timezone.utc)
    hours_remaining = max((deadline - now).total_seconds() / 3600, 0)

    # Find incomplete tasks belonging to this priority
    tasks = [
        i for i in items
        if i.get("parent_priority_id") == priority_id
        and not i.get("completed", False)
    ]

    time_needed_minutes = sum(t.get("estimated_minutes", 30) for t in tasks)
    time_needed_hours = time_needed_minutes / 60

    # Only count blocks that fall BEFORE the deadline
    all_blocks = get_available_blocks(items)
    available_blocks = [
        b for b in all_blocks
        if parse_time(b["end"]) <= deadline
    ]

    total_available_minutes = sum(b["minutes"] for b in available_blocks)
    total_available_hours = total_available_minutes / 60

    fits = total_available_hours >= time_needed_hours

    # Flexible options — items that aren't needs
    flexible_items = [
        i for i in items
        if i.get("type") != "need"
        and i.get("is_flexible", True)
        and i.get("confirmed")
    ]
    flexible_options = [
        f"Move '{i.get('title')}' to create space"
        for i in flexible_items[:3]
    ]

    if not fits:
        flexible_options.append("Break tasks into smaller chunks")
        flexible_options.append("Negotiate deadline extension")

    return {
        "priority_title": priority.get("title"),
        "hours_remaining": round(hours_remaining, 1),
        "tasks_left": len(tasks),
        "time_needed_hours": round(time_needed_hours, 1),
        "available_hours": round(total_available_hours, 1),
        "available_blocks": available_blocks,
        "fits": fits,
        "flexible_options": flexible_options
    }