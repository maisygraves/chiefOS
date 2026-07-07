from datetime import datetime, timezone, timedelta
from memory.longterm import get_schedule, save_schedule, get_changelog, save_changelog
from observability.logger import log_action

def roll_window():
    """
    Rolls the 14-day window forward:
    1. Archives confirmed past items to changelog
    2. Removes past items from schedule
    3. Ensures window extends 14 days from today
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = today_start + timedelta(days=14)

    schedule = get_schedule()
    items = schedule.get("items", [])

    past_items = []
    current_items = []

    for item in items:
        try:
            end_time = datetime.fromisoformat(item.get("end_time", ""))
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if end_time < today_start:
                past_items.append(item)
            else:
                current_items.append(item)
        except (ValueError, TypeError):
            current_items.append(item)

    # Archive past items to changelog
    if past_items:
        changelog = get_changelog()
        if not isinstance(changelog, list):
            changelog = []
        for item in past_items:
            changelog.append({
                "timestamp": now.isoformat(),
                "action": "archived",
                "item": item,
                "before": item,
                "after": None,
                "triggered_by": "roll_window"
            })
        save_changelog(changelog)

    # Save updated schedule
    schedule["items"] = current_items
    schedule["window_start"] = today_start.isoformat()
    schedule["window_end"] = window_end.isoformat()
    save_schedule(schedule)

    log_action(
        action="roll_window",
        item={"archived_count": len(past_items), "remaining_count": len(current_items)},
        triggered_by="apscheduler"
    )

    return {
        "archived": len(past_items),
        "remaining": len(current_items),
        "window_end": window_end.isoformat()
    }