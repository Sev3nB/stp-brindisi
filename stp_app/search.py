from .gtfs_time import (
    active_service_ids,
    display_time,
    duration_label,
    gtfs_seconds,
    service_day_candidates,
)


def search_stops(db, query, limit=50):
    terms = [term for term in query.strip().split() if term]
    if not terms:
        return []
    where = " AND ".join("LOWER(stop_name) LIKE LOWER(%s)" for _ in terms)
    params = [f"%{term}%" for term in terms]
    params.append(limit)
    rows = db.execute(
        f"""
        SELECT feed_id, stop_id, stop_name, stop_lat, stop_lon
        FROM stops WHERE {where}
        ORDER BY
          CASE WHEN LOWER(stop_name) LIKE LOWER(%s) THEN 0 ELSE 1 END,
          stop_name
        LIMIT %s
        """,
        params[:-1] + [f"{query.strip()}%", limit],
    ).fetchall()
    return [dict(row) for row in rows]


def list_routes(db, feed_id=None):
    params = []
    where = ""
    if feed_id:
        where = "WHERE r.feed_id = %s"
        params.append(feed_id)
    rows = db.execute(
        f"""
        SELECT r.feed_id, r.route_id, r.route_short_name, r.route_long_name,
               r.route_color, COUNT(DISTINCT t.trip_id) AS trips_count
        FROM routes r
        LEFT JOIN trips t ON t.feed_id=r.feed_id AND t.route_id=r.route_id
        {where}
        GROUP BY r.feed_id, r.route_id, r.route_short_name, r.route_long_name, r.route_color
        ORDER BY CASE r.feed_id
          WHEN 'brindisi' THEN 1 WHEN 'extraurbano' THEN 2
          WHEN 'ostuni' THEN 3 WHEN 'francavilla' THEN 4 ELSE 5 END,
          r.route_short_name, r.route_long_name
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_route_detail(db, feed_id, route_id):
    route = db.execute(
        "SELECT * FROM routes WHERE feed_id=%s AND route_id=%s",
        (feed_id, route_id),
    ).fetchone()
    if not route:
        return None

    # Per ogni direzione sceglie la corsa col maggior numero di fermate:
    # rappresenta bene il percorso principale anche quando esistono corse corte.
    representatives = db.execute(
        """
        WITH candidates AS (
          SELECT t.trip_id, t.trip_headsign, t.direction_id,
                 COUNT(st.stop_sequence) AS stops_count,
                 ROW_NUMBER() OVER (
                   PARTITION BY COALESCE(t.direction_id, -1), COALESCE(t.trip_headsign, '')
                   ORDER BY COUNT(st.stop_sequence) DESC, t.trip_id
                 ) AS position
          FROM trips t
          JOIN stop_times st ON st.feed_id=t.feed_id AND st.trip_id=t.trip_id
          WHERE t.feed_id=%s AND t.route_id=%s
          GROUP BY t.trip_id, t.trip_headsign, t.direction_id
        )
        SELECT trip_id, trip_headsign, direction_id, stops_count
        FROM candidates WHERE position=1
        ORDER BY direction_id NULLS FIRST, trip_headsign
        """,
        (feed_id, route_id),
    ).fetchall()
    variants = []
    for representative in representatives:
        stops = db.execute(
            """
            SELECT s.stop_id, s.stop_name, s.stop_lat, s.stop_lon,
                   st.stop_sequence, st.arrival_time
            FROM stop_times st
            JOIN stops s ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id
            WHERE st.feed_id=%s AND st.trip_id=%s
            ORDER BY st.stop_sequence
            """,
            (feed_id, representative["trip_id"]),
        ).fetchall()
        variants.append({**dict(representative), "stops": [dict(row) for row in stops]})
    return {**dict(route), "variants": variants}


def get_route_schedule(db, feed_id, route_id, travel_date, limit=200):
    active = active_service_ids(db, travel_date)
    service_ids = [service_id for feed, service_id in active if feed == feed_id]
    if not service_ids:
        return []
    marks = ",".join("%s" for _ in service_ids)
    rows = db.execute(
        f"""
        SELECT t.trip_id, t.trip_headsign, t.trip_short_name, t.direction_id,
               MIN(st.departure_time) AS departure_time,
               MAX(st.arrival_time) AS arrival_time,
               COUNT(st.stop_sequence) AS stops_count
        FROM trips t
        JOIN stop_times st ON st.feed_id=t.feed_id AND st.trip_id=t.trip_id
        WHERE t.feed_id=%s AND t.route_id=%s AND t.service_id IN ({marks})
        GROUP BY t.trip_id, t.trip_headsign, t.trip_short_name, t.direction_id
        ORDER BY MIN(st.departure_time), t.direction_id
        LIMIT %s
        """,
        [feed_id, route_id, *service_ids, limit],
    ).fetchall()
    return [dict(
        row,
        departure_display=display_time(row["departure_time"]),
        arrival_display=display_time(row["arrival_time"]),
    ) for row in rows]


def get_timetables(db, travel_date, feed_id=None, query=""):
    """Riepilogo giornaliero compatto, diviso per linea e direzione."""
    active = active_service_ids(db, travel_date)
    if feed_id:
        active = {(feed, service) for feed, service in active if feed == feed_id}
    if not active:
        return []

    service_marks = ",".join("(%s,%s)" for _ in active)
    params = [value for pair in sorted(active) for value in pair]
    filters = []
    if query.strip():
        filters.append("(LOWER(r.route_short_name) LIKE LOWER(%s) OR LOWER(r.route_long_name) LIKE LOWER(%s) OR LOWER(t.trip_headsign) LIKE LOWER(%s))")
        term = f"%{query.strip()}%"
        params.extend((term, term, term))
    extra_where = f"AND {' AND '.join(filters)}" if filters else ""
    rows = db.execute(
        f"""
        WITH trip_windows AS (
          SELECT t.feed_id, t.route_id, t.trip_id, t.trip_headsign,
                 MIN(st.departure_time) AS departure_time,
                 MAX(st.arrival_time) AS arrival_time
          FROM trips t JOIN stop_times st
            ON st.feed_id=t.feed_id AND st.trip_id=t.trip_id
          JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
          WHERE (t.feed_id, t.service_id) IN ({service_marks}) {extra_where}
          GROUP BY t.feed_id, t.route_id, t.trip_id, t.trip_headsign
        )
        SELECT w.feed_id, w.route_id, r.route_short_name, r.route_long_name,
               w.trip_headsign, MIN(w.departure_time) AS first_departure,
               MAX(w.departure_time) AS last_departure,
               MAX(w.arrival_time) AS last_arrival, COUNT(*) AS trips_count
        FROM trip_windows w JOIN routes r
          ON r.feed_id=w.feed_id AND r.route_id=w.route_id
        GROUP BY w.feed_id, w.route_id, r.route_short_name, r.route_long_name, w.trip_headsign
        ORDER BY CASE w.feed_id WHEN 'brindisi' THEN 1 WHEN 'extraurbano' THEN 2
          WHEN 'ostuni' THEN 3 WHEN 'francavilla' THEN 4 ELSE 5 END,
          r.route_short_name, r.route_long_name, w.trip_headsign
        """,
        params,
    ).fetchall()

    routes = {}
    for row in rows:
        key = (row["feed_id"], row["route_id"])
        route = routes.setdefault(key, {
            "feed_id": row["feed_id"], "route_id": row["route_id"],
            "route_short_name": row["route_short_name"], "route_long_name": row["route_long_name"],
            "directions": [], "trips_count": 0,
        })
        direction = dict(row)
        direction.update(
            first_display=display_time(row["first_departure"]),
            last_display=display_time(row["last_departure"]),
            arrival_display=display_time(row["last_arrival"]),
        )
        route["directions"].append(direction)
        route["trips_count"] += row["trips_count"]
    return list(routes.values())


def stops_for_map(db, query="", feed_id=None, limit=1000):
    conditions = []
    params = []
    if query.strip():
        terms = [term for term in query.strip().split() if term]
        conditions.extend("LOWER(stop_name) LIKE LOWER(%s)" for _ in terms)
        params.extend(f"%{term}%" for term in terms)
    if feed_id:
        conditions.append("feed_id=%s")
        params.append(feed_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    rows = db.execute(
        f"""
        SELECT feed_id, stop_id, stop_code, stop_name, stop_lat, stop_lon
        FROM stops {where}
        ORDER BY stop_name, feed_id
        LIMIT %s
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def nearby_stops(db, latitude, longitude, limit=8):
    rows = db.execute(
        """
        SELECT feed_id, stop_id, stop_name, stop_lat, stop_lon,
          111320 * SQRT(
            POWER(stop_lat - %s, 2) +
            POWER((stop_lon - %s) * COS(RADIANS(%s)), 2)
          ) AS distance_m
        FROM stops
        WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL
        ORDER BY distance_m
        LIMIT %s
        """,
        (latitude, longitude, latitude, limit),
    ).fetchall()
    return [dict(row, distance_m=round(float(row["distance_m"]))) for row in rows]


def get_stop_detail(db, feed_id, stop_id, travel_date):
    stop = db.execute("SELECT * FROM stops WHERE feed_id=%s AND stop_id=%s", (feed_id, stop_id)).fetchone()
    if not stop:
        return None
    routes = db.execute(
        """SELECT DISTINCT r.route_id, r.route_short_name, r.route_long_name
           FROM stop_times st JOIN trips t ON t.feed_id=st.feed_id AND t.trip_id=st.trip_id
           JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
           WHERE st.feed_id=%s AND st.stop_id=%s ORDER BY r.route_short_name""",
        (feed_id, stop_id),
    ).fetchall()
    active = [sid for feed, sid in active_service_ids(db, travel_date) if feed == feed_id]
    departures = []
    if active:
        marks = ",".join("%s" for _ in active)
        rows = db.execute(
            f"""SELECT st.departure_time, t.trip_headsign, r.route_short_name, r.route_long_name,
                       r.route_id, t.trip_id
                FROM stop_times st JOIN trips t ON t.feed_id=st.feed_id AND t.trip_id=st.trip_id
                JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
                WHERE st.feed_id=%s AND st.stop_id=%s AND t.service_id IN ({marks})
                ORDER BY st.departure_time LIMIT 150""",
            [feed_id, stop_id, *active],
        ).fetchall()
        departures = [dict(row, time_display=display_time(row["departure_time"])) for row in rows]
    return {**dict(stop), "routes": [dict(row) for row in routes], "departures": departures}


def find_direct_journeys(db, from_key, to_key, travel_date, after_seconds, limit=50):
    from_feed, from_stop = from_key.split(":", 1)
    to_feed, to_stop = to_key.split(":", 1)
    if from_feed != to_feed:
        return []

    journeys = []
    for service_date, threshold in service_day_candidates(travel_date, after_seconds):
        active = active_service_ids(db, service_date)
        service_ids = [sid for feed, sid in active if feed == from_feed]
        if not service_ids:
            continue
        marks = ",".join("%s" for _ in service_ids)
        rows = db.execute(
            f"""
            SELECT t.feed_id, t.trip_id, t.trip_headsign, t.trip_short_name,
                   t.service_id, r.route_short_name, r.route_long_name,
                   a.departure_time, a.stop_sequence AS from_sequence,
                   b.arrival_time, b.stop_sequence AS to_sequence
            FROM stop_times a
            JOIN stop_times b
              ON b.feed_id=a.feed_id AND b.trip_id=a.trip_id
            JOIN trips t ON t.feed_id=a.feed_id AND t.trip_id=a.trip_id
            JOIN routes r ON r.feed_id=t.feed_id AND r.route_id=t.route_id
            WHERE a.feed_id=%s AND a.stop_id=%s AND b.stop_id=%s
              AND b.stop_sequence > a.stop_sequence
              AND t.service_id IN ({marks})
            """,
            [from_feed, from_stop, to_stop, *service_ids],
        ).fetchall()
        for row in rows:
            departure_seconds = gtfs_seconds(row["departure_time"])
            if departure_seconds < threshold:
                continue
            arrival_seconds = gtfs_seconds(row["arrival_time"])
            item = dict(row)
            item.update(
                departure_display=display_time(row["departure_time"]),
                arrival_display=display_time(row["arrival_time"]),
                departure_seconds=departure_seconds,
                duration=duration_label(arrival_seconds - departure_seconds),
                stops_count=row["to_sequence"] - row["from_sequence"] + 1,
                service_date=service_date.isoformat(),
            )
            journeys.append(item)

    journeys.sort(key=lambda item: item["departure_seconds"])
    return journeys[:limit]


def get_journey_detail(db, feed_id, trip_id, from_stop, to_stop):
    trip = db.execute(
        """
        SELECT t.*, r.route_short_name, r.route_long_name
        FROM trips t JOIN routes r
          ON r.feed_id=t.feed_id AND r.route_id=t.route_id
        WHERE t.feed_id=%s AND t.trip_id=%s
        """,
        (feed_id, trip_id),
    ).fetchone()
    if not trip:
        return None
    bounds = db.execute(
        """
        SELECT
          (SELECT stop_sequence FROM stop_times WHERE feed_id=%s AND trip_id=%s AND stop_id=%s LIMIT 1) AS first_seq,
          (SELECT stop_sequence FROM stop_times WHERE feed_id=%s AND trip_id=%s AND stop_id=%s LIMIT 1) AS last_seq
        """,
        (feed_id, trip_id, from_stop, feed_id, trip_id, to_stop),
    ).fetchone()
    if bounds["first_seq"] is None or bounds["last_seq"] is None:
        return None
    stops = db.execute(
        """
        SELECT s.stop_id, s.stop_name, s.stop_lat, s.stop_lon,
               st.arrival_time, st.departure_time, st.stop_sequence
        FROM stop_times st JOIN stops s
          ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id
        WHERE st.feed_id=%s AND st.trip_id=%s
          AND st.stop_sequence BETWEEN %s AND %s
        ORDER BY st.stop_sequence
        """,
        (feed_id, trip_id, bounds["first_seq"], bounds["last_seq"]),
    ).fetchall()
    result = dict(trip)
    result["stops"] = [dict(stop, time_display=display_time(stop["arrival_time"])) for stop in stops]
    return result
