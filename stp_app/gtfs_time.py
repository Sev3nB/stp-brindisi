from datetime import date, datetime, timedelta


WEEKDAYS = (
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
)


def parse_gtfs_date(value):
    return datetime.strptime(value, "%Y%m%d").date()


def gtfs_seconds(value):
    """Converte anche orari GTFS oltre le 24:00 in secondi."""
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def display_time(value):
    total = gtfs_seconds(value) % (24 * 3600)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


def duration_label(seconds):
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes = remainder // 60
    if hours:
        return f"{hours} h {minutes:02d} min"
    return f"{minutes} min"


def active_service_ids(db, travel_date: date):
    compact = travel_date.strftime("%Y%m%d")
    weekday = WEEKDAYS[travel_date.weekday()]
    rows = db.execute(
        f"""
        SELECT feed_id, service_id
        FROM calendars
        WHERE start_date <= %s AND end_date >= %s AND {weekday} = 1
        """,
        (compact, compact),
    ).fetchall()
    active = {(row["feed_id"], row["service_id"]) for row in rows}

    exceptions = db.execute(
        "SELECT feed_id, service_id, exception_type FROM calendar_dates WHERE date = %s",
        (compact,),
    ).fetchall()
    for row in exceptions:
        key = (row["feed_id"], row["service_id"])
        if row["exception_type"] == 1:
            active.add(key)
        elif row["exception_type"] == 2:
            active.discard(key)
    return active


def service_day_candidates(travel_date, after_seconds):
    """Dopo mezzanotte considera anche le corse 24:xx del giorno precedente."""
    yield travel_date, after_seconds
    if after_seconds < 4 * 3600:
        yield travel_date - timedelta(days=1), after_seconds + 24 * 3600
