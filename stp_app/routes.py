import json
from datetime import date, datetime

from flask import Blueprint, abort, current_app, jsonify, render_template, request

from .db import get_db
from .gtfs_time import gtfs_seconds
from .geocoding import search_places
from .search import (
    find_direct_journeys, get_journey_detail, get_route_detail, get_route_schedule, get_stop_detail, get_timetables,
    list_routes, nearby_stops, search_stops, stops_for_map,
)
from .trip_planner import plan_journeys

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    ready = bool(current_app.config.get("DATABASE_URL"))
    metadata = []
    if ready:
        try:
            with get_db() as db:
                metadata = db.execute("SELECT * FROM feeds ORDER BY feed_id").fetchall()
        except Exception:
            ready = False
    return render_template("index.html", today=date.today().isoformat(), ready=ready, metadata=metadata)


@bp.get("/api/stops")
def stops_api():
    query = request.args.get("q", "")
    if len(query.strip()) < 2:
        return jsonify([])
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    with get_db() as db:
        return jsonify(search_stops(db, query, limit=limit))


@bp.get("/api/nearby-stops")
def nearby_stops_api():
    try:
        latitude = float(request.args["lat"])
        longitude = float(request.args["lon"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Coordinate non valide"}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"error": "Coordinate non valide"}), 400
    with get_db() as db:
        return jsonify(nearby_stops(db, latitude, longitude))


@bp.get("/api/places")
def places_api():
    query = request.args.get("q", "").strip()
    if len(query) < 3:
        return jsonify([])
    try:
        return jsonify(search_places(query))
    except Exception:
        return jsonify([])


def _point_from_form(name):
    raw = request.form.get(name, "")
    try:
        point = json.loads(raw)
        latitude, longitude = float(point["lat"]), float(point["lon"])
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError
        return {"name": str(point.get("name") or "Posizione"), "lat": latitude, "lon": longitude}
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


@bp.post("/plan")
def automatic_plan():
    origin = _point_from_form("origin_json")
    destination = _point_from_form("destination_json")
    date_text = request.form.get("date", "")
    time_text = request.form.get("time", "00:00")
    if not origin or not destination:
        return render_template("planner_results.html", error="Seleziona una partenza e un arrivo validi.", journeys=[]), 400
    try:
        travel_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        departure_seconds = gtfs_seconds(f"{time_text}:00" if len(time_text) == 5 else time_text)
    except ValueError:
        return render_template("planner_results.html", error="Data o ora non valida.", journeys=[]), 400
    try:
        with get_db() as db:
            result = plan_journeys(db, origin, destination, travel_date, departure_seconds)
    except Exception:
        current_app.logger.exception("Errore durante il calcolo del percorso")
        return render_template(
            "planner_results.html",
            error="Il calcolo non è disponibile in questo momento. Riprova tra poco.",
            journeys=[], origin=origin, destination=destination, date=date_text, time=time_text,
        ), 503
    return render_template(
        "planner_results.html", error=result.get("reason"), journeys=result["journeys"],
        origin=origin, destination=destination, date=date_text, time=time_text,
    )


@bp.get("/lines")
def lines():
    feed_id = request.args.get("feed", "")
    with get_db() as db:
        routes = list_routes(db, feed_id or None)
    groups = {
        "brindisi": "Urbane di Brindisi",
        "extraurbano": "Extraurbane",
        "ostuni": "Urbane di Ostuni",
        "francavilla": "Urbane di Francavilla Fontana",
    }
    return render_template("lines.html", routes=routes, groups=groups, active_feed=feed_id)


@bp.get("/timetables")
def timetables():
    date_text = request.args.get("date", date.today().isoformat())
    feed_id = request.args.get("feed", "")
    query = request.args.get("q", "").strip()
    try:
        travel_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        travel_date = date.today()
        date_text = travel_date.isoformat()
    with get_db() as db:
        routes = get_timetables(db, travel_date, feed_id or None, query)
    groups = {
        "brindisi": "Urbane di Brindisi", "extraurbano": "Extraurbane",
        "ostuni": "Urbane di Ostuni", "francavilla": "Urbane di Francavilla Fontana",
    }
    return render_template(
        "timetables.html", routes=routes, groups=groups, selected_date=date_text,
        active_feed=feed_id, query=query,
    )


@bp.get("/line/<feed_id>/<route_id>")
def line_detail(feed_id, route_id):
    date_text = request.args.get("date", date.today().isoformat())
    try:
        travel_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        travel_date = date.today()
        date_text = travel_date.isoformat()
    with get_db() as db:
        route = get_route_detail(db, feed_id, route_id)
        schedule = get_route_schedule(db, feed_id, route_id, travel_date) if route else []
    if not route:
        abort(404)
    return render_template("line.html", route=route, schedule=schedule, selected_date=date_text)


@bp.get("/stops")
def stops_map():
    query = request.args.get("q", "Brindisi").strip()
    feed_id = request.args.get("feed", "")
    with get_db() as db:
        stops = stops_for_map(db, query, feed_id or None)
    return render_template("stops.html", stops=stops, query=query, active_feed=feed_id)


@bp.get("/stop/<feed_id>/<stop_id>")
def stop_detail(feed_id, stop_id):
    date_text = request.args.get("date", date.today().isoformat())
    try:
        travel_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        travel_date = date.today(); date_text = travel_date.isoformat()
    with get_db() as db:
        stop = get_stop_detail(db, feed_id, stop_id, travel_date)
    if not stop:
        abort(404)
    return render_template("stop.html", stop=stop, selected_date=date_text)


@bp.get("/search")
def search():
    from_key = request.args.get("from_stop", "")
    to_key = request.args.get("to_stop", "")
    date_text = request.args.get("date", "")
    time_text = request.args.get("time", "00:00")
    if not from_key or not to_key or from_key == to_key:
        return render_template("results.html", error="Scegli due fermate diverse.", journeys=[])
    try:
        travel_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        after_seconds = gtfs_seconds(f"{time_text}:00" if len(time_text) == 5 else time_text)
    except ValueError:
        return render_template("results.html", error="Data o ora non valida.", journeys=[])

    with get_db() as db:
        names = db.execute(
            """SELECT feed_id || ':' || stop_id AS key, stop_name
               FROM stops WHERE feed_id || ':' || stop_id IN (%s, %s)""",
            (from_key, to_key),
        ).fetchall()
        name_map = {row["key"]: row["stop_name"] for row in names}
        journeys = find_direct_journeys(db, from_key, to_key, travel_date, after_seconds)
    return render_template(
        "results.html", journeys=journeys, error=None,
        from_key=from_key, to_key=to_key,
        from_name=name_map.get(from_key, from_key), to_name=name_map.get(to_key, to_key),
        date=date_text, time=time_text,
    )


@bp.get("/journey/<feed_id>/<trip_id>")
def journey(feed_id, trip_id):
    from_stop = request.args.get("from", "")
    to_stop = request.args.get("to", "")
    with get_db() as db:
        detail = get_journey_detail(db, feed_id, trip_id, from_stop, to_stop)
    if not detail:
        abort(404)
    return render_template("journey.html", journey=detail)
