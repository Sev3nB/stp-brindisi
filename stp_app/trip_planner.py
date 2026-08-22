from datetime import date
from math import asin, cos, radians, sin, sqrt

from .gtfs_time import active_service_ids, display_time, duration_label

WALK_SPEED_MPS = 1.25
MAX_ACCESS_METERS = 2200
PREFERRED_ACCESS_METERS = 1400
MAX_TRANSFER_METERS = 350
MAX_WAIT_SECONDS = 2 * 3600
MAX_RIDES = 3
MAX_FRONTIER = 260


def clock(seconds):
    value = seconds % (24 * 3600)
    return f"{value // 3600:02d}:{(value % 3600) // 60:02d}"


def haversine(lat1, lon1, lat2, lon2):
    radius = 6_371_000
    p1, p2 = radians(lat1), radians(lat2)
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    value = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(value))


def walking_seconds(distance):
    return round(distance / WALK_SPEED_MPS)


def all_stops(db):
    rows = db.execute(
        """SELECT feed_id, stop_id, stop_name, stop_lat, stop_lon
           FROM stops WHERE stop_lat IS NOT NULL AND stop_lon IS NOT NULL"""
    ).fetchall()
    return [{**dict(row), "key": f'{row["feed_id"]}:{row["stop_id"]}'} for row in rows]


def candidate_stops(stops, point, limit=12, max_distance=MAX_ACCESS_METERS):
    candidates = []
    for stop in stops:
        distance = haversine(point["lat"], point["lon"], stop["stop_lat"], stop["stop_lon"])
        if distance <= max_distance:
            candidates.append((distance, stop))
    candidates.sort(key=lambda item: item[0])
    return candidates[:limit]


def endpoint_candidates(stops, point):
    """Preferisce fermate davvero vicine, allargando il raggio solo se necessario."""
    preferred = candidate_stops(stops, point, limit=10, max_distance=PREFERRED_ACCESS_METERS)
    if preferred:
        return preferred
    return candidate_stops(stops, point, limit=4, max_distance=MAX_ACCESS_METERS)


def journey_quality(segments, direct_distance, duration_seconds, transfers):
    """Scarta itinerari formalmente possibili ma inutili per una persona reale."""
    buses = [segment for segment in segments if segment["type"] == "bus"]
    walking = sum(segment.get("distance", 0) for segment in segments if segment["type"] == "walk")
    bus_distance = sum(segment.get("ride_distance", 0) for segment in buses)
    bus_stops = sum(segment.get("stops_count", 0) for segment in buses)

    if not buses or bus_distance < 600:
        return None
    # Una sola fermata è accettabile solo se rappresenta una tratta lunga reale.
    if len(buses) == 1 and bus_stops <= 1 and bus_distance < 1500:
        return None
    # Non proporre una corriera se quasi tutto il percorso resterebbe comunque a piedi.
    if direct_distance > 500 and walking >= direct_distance * .80:
        return None
    if walking > 1800:
        return None

    walking_penalty = walking_seconds(walking) * .75
    transfer_penalty = transfers * 8 * 60
    complexity_penalty = max(0, len(buses) - 1) * 2 * 60
    return duration_seconds + walking_penalty + transfer_penalty + complexity_penalty


def _time_sql(column):
    return (
        f"split_part({column}, ':', 1)::int * 3600 + "
        f"split_part({column}, ':', 2)::int * 60 + split_part({column}, ':', 3)::int"
    )


def ride_connections(db, frontier, services):
    if not frontier or not services:
        return []
    frontier = sorted(frontier.values(), key=lambda label: label["arrival"])[:MAX_FRONTIER]
    values = ",".join("(%s,%s,%s)" for _ in frontier)
    service_values = ",".join("(%s,%s)" for _ in services)
    params = []
    for label in frontier:
        feed_id, stop_id = label["key"].split(":", 1)
        params.extend((feed_id, stop_id, label["arrival"]))
    for feed_id, service_id in services:
        params.extend((feed_id, service_id))

    dep_seconds = _time_sql("board.departure_time")
    arr_seconds = _time_sql("downstream.arrival_time")
    rows = db.execute(
        f"""
        WITH frontier(feed_id, stop_id, ready_sec) AS (VALUES {values}),
        possible AS (
          SELECT t.feed_id, t.trip_id, t.route_id, t.trip_headsign,
                 board.stop_id AS board_stop_id, board.stop_sequence AS board_sequence,
                 {dep_seconds} AS departure_sec, f.ready_sec,
                 ROW_NUMBER() OVER (
                   PARTITION BY t.feed_id, t.trip_id
                   ORDER BY board.stop_sequence
                 ) AS choice
          FROM frontier f
          JOIN stop_times board ON board.feed_id=f.feed_id AND board.stop_id=f.stop_id
          JOIN trips t ON t.feed_id=board.feed_id AND t.trip_id=board.trip_id
          WHERE (t.feed_id, t.service_id) IN ({service_values})
            AND {dep_seconds} >= f.ready_sec
            AND {dep_seconds} <= f.ready_sec + {MAX_WAIT_SECONDS}
        ), boardings AS (
          SELECT * FROM possible WHERE choice=1
        )
        SELECT b.feed_id, b.trip_id, b.route_id, b.trip_headsign,
               b.board_stop_id, b.board_sequence, b.departure_sec, b.ready_sec,
               downstream.stop_id AS alight_stop_id,
               downstream.stop_sequence AS alight_sequence,
               {arr_seconds} AS arrival_sec,
               r.route_short_name, r.route_long_name
        FROM boardings b
        JOIN stop_times downstream
          ON downstream.feed_id=b.feed_id AND downstream.trip_id=b.trip_id
         AND downstream.stop_sequence>b.board_sequence
        JOIN routes r ON r.feed_id=b.feed_id AND r.route_id=b.route_id
        ORDER BY arrival_sec
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def add_walking_transfers(labels, newly_reached, stops):
    additions = {}
    stop_by_key = {stop["key"]: stop for stop in stops}
    for label in sorted(newly_reached.values(), key=lambda item: item["arrival"])[:MAX_FRONTIER]:
        origin = stop_by_key[label["key"]]
        for target in stops:
            if target["key"] == label["key"]:
                continue
            # Bounding box economico prima della distanza sferica.
            if abs(target["stop_lat"] - origin["stop_lat"]) > .004 or abs(target["stop_lon"] - origin["stop_lon"]) > .005:
                continue
            distance = haversine(origin["stop_lat"], origin["stop_lon"], target["stop_lat"], target["stop_lon"])
            if distance > MAX_TRANSFER_METERS:
                continue
            arrival = label["arrival"] + walking_seconds(distance) + 60
            existing = labels.get(target["key"])
            pending = additions.get(target["key"])
            if (existing and existing["arrival"] <= arrival) or (pending and pending["arrival"] <= arrival):
                continue
            additions[target["key"]] = {
                "key": target["key"], "arrival": arrival, "rides": label["rides"],
                "walk": label["walk"] + distance, "previous": label,
                "segment": {
                    "type": "walk", "from_name": origin["stop_name"], "to_name": target["stop_name"],
                    "distance": round(distance), "duration": walking_seconds(distance) + 60,
                    "from_lat": origin["stop_lat"], "from_lon": origin["stop_lon"],
                    "to_lat": target["stop_lat"], "to_lon": target["stop_lon"],
                    "transfer": True, "departure": label["arrival"], "arrival": arrival,
                },
            }
    labels.update(additions)
    newly_reached.update(additions)


def reconstruct(label):
    segments = []
    current = label
    while current and current.get("segment"):
        segments.append(current["segment"])
        current = current.get("previous")
    segments.reverse()
    return segments


def hydrate_bus_segments(db, segments):
    for segment in segments:
        if segment["type"] != "bus":
            continue
        rows = db.execute(
            """
            SELECT s.stop_name, s.stop_lat, s.stop_lon, st.stop_sequence, st.arrival_time
            FROM stop_times st JOIN stops s
              ON s.feed_id=st.feed_id AND s.stop_id=st.stop_id
            WHERE st.feed_id=%s AND st.trip_id=%s
              AND st.stop_sequence BETWEEN %s AND %s
            ORDER BY st.stop_sequence
            """,
            (segment["feed_id"], segment["trip_id"], segment["board_sequence"], segment["alight_sequence"]),
        ).fetchall()
        segment["stops"] = [dict(row) for row in rows]


def plan_journeys(db, origin, destination, travel_date: date, departure_seconds):
    stops = all_stops(db)
    starts = endpoint_candidates(stops, origin)
    ends = endpoint_candidates(stops, destination)
    if not starts or not ends:
        return {"journeys": [], "reason": "Nessuna fermata raggiungibile vicino a uno dei due punti."}

    stop_by_key = {stop["key"]: stop for stop in stops}
    destination_walks = {stop["key"]: distance for distance, stop in ends}
    labels = {}
    frontier = {}
    for distance, stop in starts:
        duration = walking_seconds(distance)
        label = {
            "key": stop["key"], "arrival": departure_seconds + duration,
            "rides": 0, "walk": distance, "previous": None,
            "segment": {
                "type": "walk", "from_name": origin["name"], "to_name": stop["stop_name"],
                    "distance": round(distance), "duration": duration,
                "from_lat": origin["lat"], "from_lon": origin["lon"],
                    "to_lat": stop["stop_lat"], "to_lon": stop["stop_lon"], "access": True,
                    "departure": departure_seconds, "arrival": departure_seconds + duration,
            },
        }
        labels[stop["key"]] = label
        frontier[stop["key"]] = label

    services = active_service_ids(db, travel_date)
    options = []
    signatures = set()
    for ride_round in range(1, MAX_RIDES + 1):
        rows = ride_connections(db, frontier, services)
        reached = {}
        for row in rows:
            board_key = f'{row["feed_id"]}:{row["board_stop_id"]}'
            alight_key = f'{row["feed_id"]}:{row["alight_stop_id"]}'
            previous = frontier.get(board_key) or labels.get(board_key)
            if not previous:
                continue
            arrival = row["arrival_sec"]
            existing = labels.get(alight_key)
            pending = reached.get(alight_key)
            if (existing and existing["arrival"] <= arrival and existing["rides"] <= ride_round) or (pending and pending["arrival"] <= arrival):
                continue
            board_stop = stop_by_key[board_key]
            alight_stop = stop_by_key[alight_key]
            label = {
                "key": alight_key, "arrival": arrival, "rides": ride_round,
                "walk": previous["walk"], "previous": previous,
                "segment": {
                    "type": "bus", "feed_id": row["feed_id"], "trip_id": row["trip_id"],
                    "route_id": row["route_id"], "route_short_name": row["route_short_name"],
                    "route_long_name": row["route_long_name"], "headsign": row["trip_headsign"],
                    "from_name": board_stop["stop_name"], "to_name": alight_stop["stop_name"],
                    "from_lat": board_stop["stop_lat"], "from_lon": board_stop["stop_lon"],
                    "to_lat": alight_stop["stop_lat"], "to_lon": alight_stop["stop_lon"],
                    "stops_count": row["alight_sequence"] - row["board_sequence"],
                    "ride_distance": round(haversine(
                        board_stop["stop_lat"], board_stop["stop_lon"],
                        alight_stop["stop_lat"], alight_stop["stop_lon"],
                    )),
                    "departure": row["departure_sec"], "arrival": arrival,
                    "departure_display": display_time(f'{row["departure_sec"]//3600:02d}:{(row["departure_sec"]%3600)//60:02d}:00'),
                    "arrival_display": display_time(f'{arrival//3600:02d}:{(arrival%3600)//60:02d}:00'),
                    "board_sequence": row["board_sequence"], "alight_sequence": row["alight_sequence"],
                },
            }
            reached[alight_key] = label
        labels.update(reached)
        add_walking_transfers(labels, reached, stops)

        for key, label in reached.items():
            if key not in destination_walks:
                continue
            final_distance = destination_walks[key]
            stop = stop_by_key[key]
            final_duration = walking_seconds(final_distance)
            final_label = {
                "arrival": label["arrival"] + final_duration, "rides": label["rides"],
                "walk": label["walk"] + final_distance, "previous": label,
                "segment": {
                    "type": "walk", "from_name": stop["stop_name"], "to_name": destination["name"],
                    "distance": round(final_distance), "duration": final_duration,
                    "from_lat": stop["stop_lat"], "from_lon": stop["stop_lon"],
                    "to_lat": destination["lat"], "to_lon": destination["lon"], "egress": True,
                    "departure": label["arrival"], "arrival": label["arrival"] + final_duration,
                },
            }
            segments = reconstruct(final_label)
            previous_arrival = departure_seconds
            for segment in segments:
                segment["wait_before"] = max(0, segment["departure"] - previous_arrival) if segment["type"] == "bus" else 0
                segment["departure_display"] = clock(segment["departure"])
                segment["arrival_display"] = clock(segment["arrival"])
                previous_arrival = segment["arrival"]
            signature = tuple((s.get("trip_id"), s.get("from_name"), s.get("to_name")) for s in segments if s["type"] == "bus")
            if signature in signatures:
                continue
            duration_seconds = final_label["arrival"] - departure_seconds
            transfers = max(0, final_label["rides"] - 1)
            direct_distance = haversine(origin["lat"], origin["lon"], destination["lat"], destination["lon"])
            quality = journey_quality(segments, direct_distance, duration_seconds, transfers)
            if quality is None:
                continue
            signatures.add(signature)
            options.append({
                "arrival": final_label["arrival"], "departure": departure_seconds,
                "duration_seconds": duration_seconds,
                "duration": duration_label(duration_seconds),
                "arrival_display": clock(final_label["arrival"]),
                "transfers": transfers, "quality": quality,
                "walking_meters": round(final_label["walk"]), "segments": segments,
            })
        frontier = reached
        if not frontier:
            break

    # Bilancia durata, cammino e cambi: la prima alternativa deve essere utile,
    # non soltanto matematicamente la prima ad arrivare.
    options.sort(key=lambda item: (item["quality"], item["arrival"], item["transfers"]))
    selected = options[:3]
    for index, option in enumerate(selected):
        if index == 0:
            option["label"] = "Consigliato"
        elif option["duration_seconds"] < selected[0]["duration_seconds"]:
            option["label"] = "Più veloce"
        elif option["transfers"] < selected[0]["transfers"]:
            option["label"] = "Meno cambi"
        else:
            option["label"] = "Alternativa"
        hydrate_bus_segments(db, option["segments"])
    reason = None if selected else (
        "Non risultano corse che riducano davvero il tragitto a piedi: "
        "le combinazioni trovate erano troppo brevi o richiedevano camminate eccessive."
    )
    return {"journeys": selected, "reason": reason, "origin_candidates": len(starts), "destination_candidates": len(ends)}
