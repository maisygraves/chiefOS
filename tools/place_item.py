from memory.longterm import get_schedule, save_schedule
from observability.logger import log_action
from datetime import datetime, timezone, timedelta
import uuid

def parse_time(t: str) -> datetime:
    try:
        dt = datetime.fromisoformat(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise ValueError(f"Cannot parse time: {t}")

def times_overlap(start1, end1, start2, end2) -> bool:
    """Two items overlap if one starts before the other ends."""
    return start1 < end2 and start2 < end1

def expand_recurring(item: dict, window_start: datetime, window_end: datetime) -> list[dict]:
    """
    Expands a recurring item into individual instances across the 14-day window.
    
    Each instance is a copy of the item with:
    - A unique ID
    - Adjusted start/end times for that specific day
    - A reference back to the parent recurring item
    
    Recurrence patterns:
    - "daily"    — every day in the window
    - "weekdays" — Monday through Friday
    - "weekends" — Saturday and Sunday
    - "weekly"   — same day of week as original start
    """
    pattern = item.get("recurrence_pattern")
    if not pattern:
        return [item]

    try:
        original_start = parse_time(item["start_time"])
        original_end = parse_time(item["end_time"])
    except (ValueError, KeyError):
        return [item]

    # Duration stays the same for every instance
    duration = original_end - original_start

    # Time of day stays the same — only the date changes
    start_hour = original_start.hour
    start_minute = original_start.minute

    instances = []
    current = window_start

    while current <= window_end:
        day_of_week = current.weekday()  # 0=Monday, 6=Sunday

        should_include = False
        if pattern == "daily":
            should_include = True
        elif pattern == "weekdays":
            should_include = day_of_week < 5  # Mon-Fri
        elif pattern == "weekends":
            should_include = day_of_week >= 5  # Sat-Sun
        elif pattern == "weekly":
            should_include = day_of_week == original_start.weekday()

        if should_include:
            instance_start = current.replace(
                hour=start_hour,
                minute=start_minute,
                second=0,
                microsecond=0
            )
            instance_end = instance_start + duration

            instance = {
                **item,
                "id": str(uuid.uuid4()),
                "start_time": instance_start.isoformat(),
                "end_time": instance_end.isoformat(),
                "parent_recurring_id": item.get("id", item.get("title")),
                "confirmed": True
            }
            instances.append(instance)

        current += timedelta(days=1)

    return instances

def split_at_midnight(instance: dict) -> list[dict]:
    """
    If an item crosses midnight, split it into two instances:
    - One from start to midnight
    - One from midnight to end (next day)
    
    This ensures the day ribbon displays correctly.
    """
    try:
        start = parse_time(instance["start_time"])
        end = parse_time(instance["end_time"])
    except (ValueError, KeyError):
        return [instance]

    # Check if item crosses midnight
    midnight = start.replace(hour=23, minute=59, second=59)
    next_midnight = (start + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    if end.date() <= start.date():
        # Doesn't cross midnight
        return [instance]

    # First part — start to midnight
    first = {
        **instance,
        "id": str(uuid.uuid4()),
        "end_time": midnight.isoformat(),
    }

    # Second part — midnight to end
    second = {
        **instance,
        "id": str(uuid.uuid4()),
        "start_time": next_midnight.isoformat(),
        "parent_recurring_id": instance.get("parent_recurring_id", instance.get("id"))
    }

    return [first, second]

def check_single_conflict(new_start, new_end, items: list) -> dict | None:
    """
    Checks one time range against all existing items.
    Returns the conflicting item or None.
    """
    for existing in items:
        try:
            ex_start = parse_time(existing["start_time"])
            ex_end = parse_time(existing["end_time"])
        except (ValueError, KeyError):
            continue

        if times_overlap(new_start, new_end, ex_start, ex_end):
            return existing
    return None


def place_confirmed_item(item: dict) -> dict:
    """
    Places confirmed item into schedule.
    
    For recurring items — expands across the 14-day window first,
    then checks each instance for conflicts before placing any.
    
    Detects conflicts, flags immediately.
    Never places over a Need.
    """
    schedule = get_schedule()
    items = schedule.get("items", [])

    # Get window bounds for recurring expansion
    now = datetime.now(timezone.utc)
    window_start_str = schedule.get("window_start")
    window_end_str = schedule.get("window_end")

    try:
        window_start = parse_time(window_start_str) if window_start_str else now
        window_end = parse_time(window_end_str) if window_end_str else now + timedelta(days=14)
    except ValueError:
        window_start = now
        window_end = now + timedelta(days=14)

    # Validate the item has parseable times
    try:
        parse_time(item["start_time"])
        parse_time(item["end_time"])
    except (ValueError, KeyError) as e:
        return {
            "success": False,
            "flag": f"Invalid time format: {e}",
            "conflict_item": None
        }

    # Expand recurring items into instances
    is_recurring = item.get("recurring", False) and item.get("recurrence_pattern")
    if is_recurring:
        instances = expand_recurring(item, window_start, window_end)
    else:
        instances = [item]

    # Split any instances that cross midnight
    split_instances = []
    for instance in instances:
        split_instances.extend(split_at_midnight(instance))
    instances = split_instances

    # Check ALL instances for conflicts before placing any
    # — we don't want to place half a recurring series
    for instance in instances:
        try:
            inst_start = parse_time(instance["start_time"])
            inst_end = parse_time(instance["end_time"])
        except (ValueError, KeyError):
            continue

        conflict = check_single_conflict(inst_start, inst_end, items)
        if conflict:
            if conflict.get("type") == "need":
                return {
                    "success": False,
                    "flag": f"Conflicts with a need: {conflict.get('title')}. Needs cannot be moved.",
                    "conflict_item": conflict
                }
            return {
                "success": False,
                "flag": f"Conflicts with: {conflict.get('title')} on {instance['start_time'][:10]}. Want to reschedule?",
                "conflict_item": conflict
            }

    # No conflicts — place all instances
    placed_count = 0
    for instance in instances:
        instance["confirmed"] = True
        if "id" not in instance:
            instance["id"] = str(uuid.uuid4())
        items.append(instance)
        placed_count += 1

        log_action(
            action="placed",
            item=instance,
            before=None,
            after=instance,
            triggered_by="user_confirmation"
        )

    schedule["items"] = items
    save_schedule(schedule)

    if is_recurring:
        return {
            "success": True,
            "flag": None,
            "placed_count": placed_count,
            "message": f"Placed {placed_count} instances across the 14-day window."
        }

    return {"success": True, "flag": None, "placed_count": 1}