import unittest
from datetime import date

from stp_app.gtfs_time import active_service_ids, display_time, gtfs_seconds
from stp_app.search import get_timetables
from stp_app.trip_planner import candidate_stops, endpoint_candidates, haversine, journey_quality, walking_seconds


class GtfsTimeTests(unittest.TestCase):
    def test_times_after_midnight(self):
        self.assertEqual(gtfs_seconds("25:10:00"), 90600)
        self.assertEqual(display_time("25:10:00"), "01:10")

    def test_calendar_exceptions_override_weekday(self):
        class Result:
            def __init__(self, rows): self.rows = rows
            def fetchall(self): return self.rows

        class FakeDb:
            def execute(self, query, _params):
                if "FROM calendars" in query:
                    return Result([{"feed_id": "x", "service_id": "regular"}])
                return Result([
                    {"feed_id": "x", "service_id": "regular", "exception_type": 2},
                    {"feed_id": "x", "service_id": "special", "exception_type": 1},
                ])

        db = FakeDb()
        active = active_service_ids(db, date(2026, 8, 24))
        self.assertNotIn(("x", "regular"), active)
        self.assertIn(("x", "special"), active)

    def test_nearby_stop_candidates_are_sorted_and_limited(self):
        stops = [
            {"key": "x:far", "stop_lat": 40.010, "stop_lon": 18.0},
            {"key": "x:near", "stop_lat": 40.001, "stop_lon": 18.0},
            {"key": "x:outside", "stop_lat": 41.0, "stop_lon": 18.0},
        ]
        result = candidate_stops(stops, {"lat": 40.0, "lon": 18.0}, limit=2)
        self.assertEqual([item[1]["key"] for item in result], ["x:near", "x:far"])

    def test_walking_estimate(self):
        distance = haversine(40.0, 18.0, 40.001, 18.0)
        self.assertGreater(distance, 100)
        self.assertEqual(walking_seconds(125), 100)

    def test_endpoint_candidates_do_not_add_distant_stops_when_nearby_exist(self):
        stops = [
            {"key": "x:near", "stop_lat": 40.001, "stop_lon": 18.0},
            {"key": "x:distant", "stop_lat": 40.015, "stop_lon": 18.0},
        ]
        result = endpoint_candidates(stops, {"lat": 40.0, "lon": 18.0})
        self.assertEqual([item[1]["key"] for item in result], ["x:near"])

    def test_rejects_one_stop_bus_that_saves_almost_no_walking(self):
        segments = [
            {"type": "walk", "distance": 400},
            {"type": "bus", "ride_distance": 300, "stops_count": 1},
            {"type": "walk", "distance": 500},
        ]
        self.assertIsNone(journey_quality(segments, 1200, 900, 0))

    def test_keeps_a_meaningful_bus_journey(self):
        segments = [
            {"type": "walk", "distance": 250},
            {"type": "bus", "ride_distance": 8000, "stops_count": 9},
            {"type": "walk", "distance": 300},
        ]
        self.assertIsNotNone(journey_quality(segments, 8500, 2400, 0))

    def test_timetable_groups_directions_under_the_same_line(self):
        class Result:
            def __init__(self, rows): self.rows = rows
            def fetchall(self): return self.rows

        class FakeDb:
            def execute(self, query, _params):
                if "FROM calendars" in query:
                    return Result([{"feed_id": "brindisi", "service_id": "weekday"}])
                if "FROM calendar_dates" in query:
                    return Result([])
                return Result([
                    {"feed_id": "brindisi", "route_id": "7", "route_short_name": "7",
                     "route_long_name": "Centro - Ospedale", "trip_headsign": "Ospedale",
                     "first_departure": "06:30:00", "last_departure": "20:30:00",
                     "last_arrival": "21:00:00", "trips_count": 12},
                    {"feed_id": "brindisi", "route_id": "7", "route_short_name": "7",
                     "route_long_name": "Centro - Ospedale", "trip_headsign": "Centro",
                     "first_departure": "06:45:00", "last_departure": "20:45:00",
                     "last_arrival": "21:15:00", "trips_count": 11},
                ])

        result = get_timetables(FakeDb(), date(2026, 8, 24))
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["directions"]), 2)
        self.assertEqual(result[0]["trips_count"], 23)


if __name__ == "__main__":
    unittest.main()
