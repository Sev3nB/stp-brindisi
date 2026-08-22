#!/usr/bin/env python3
import csv
import hashlib
import io
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATABASE_URL, FEEDS, RAW_DIR  # noqa: E402


SCHEMA = """
CREATE SCHEMA IF NOT EXISTS gtfs;
SET search_path TO gtfs, public;

CREATE TABLE IF NOT EXISTS feeds (
  feed_id text PRIMARY KEY, source_url text NOT NULL, updated_at timestamptz NOT NULL,
  sha256 text NOT NULL, start_date text, end_date text, status text NOT NULL
);
CREATE TABLE IF NOT EXISTS stops (
  feed_id text NOT NULL, stop_id text NOT NULL, stop_code text,
  stop_name text NOT NULL, stop_lat double precision, stop_lon double precision,
  wheelchair_boarding integer, PRIMARY KEY(feed_id, stop_id)
);
CREATE TABLE IF NOT EXISTS routes (
  feed_id text NOT NULL, route_id text NOT NULL, route_short_name text,
  route_long_name text, route_type integer, route_color text,
  route_text_color text, PRIMARY KEY(feed_id, route_id)
);
CREATE TABLE IF NOT EXISTS trips (
  feed_id text NOT NULL, route_id text NOT NULL, service_id text NOT NULL,
  trip_id text NOT NULL, trip_headsign text, trip_short_name text,
  direction_id integer, wheelchair_accessible integer,
  PRIMARY KEY(feed_id, trip_id)
);
CREATE TABLE IF NOT EXISTS stop_times (
  feed_id text NOT NULL, trip_id text NOT NULL, arrival_time text NOT NULL,
  departure_time text NOT NULL, stop_id text NOT NULL, stop_sequence integer NOT NULL,
  pickup_type integer, drop_off_type integer,
  PRIMARY KEY(feed_id, trip_id, stop_sequence)
);
CREATE TABLE IF NOT EXISTS calendars (
  feed_id text NOT NULL, service_id text NOT NULL,
  monday integer, tuesday integer, wednesday integer, thursday integer,
  friday integer, saturday integer, sunday integer,
  start_date text, end_date text, PRIMARY KEY(feed_id, service_id)
);
CREATE TABLE IF NOT EXISTS calendar_dates (
  feed_id text NOT NULL, service_id text NOT NULL, date text NOT NULL,
  exception_type integer NOT NULL,
  PRIMARY KEY(feed_id, service_id, date, exception_type)
);
CREATE INDEX IF NOT EXISTS idx_stops_name ON stops(lower(stop_name));
CREATE INDEX IF NOT EXISTS idx_stop_times_stop ON stop_times(feed_id, stop_id, departure_time);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip ON stop_times(feed_id, trip_id, stop_sequence);
CREATE INDEX IF NOT EXISTS idx_trips_service ON trips(feed_id, service_id);
CREATE INDEX IF NOT EXISTS idx_calendar_dates_date ON calendar_dates(date);
"""


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "STP-Personal-App/2.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"PK"):
        raise ValueError("La risposta STP non è un archivio ZIP")
    return data


def csv_rows(archive, filename):
    if filename not in archive.namelist():
        return
    raw = archive.read(filename)
    text = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig", newline="")
    yield from csv.DictReader(text)


def integer(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def copy_rows(cursor, table, columns, rows):
    count = 0
    names = ", ".join(columns)
    with cursor.copy(f"COPY {table} ({names}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def import_feed(cursor, feed_id, url, payload):
    archive = zipfile.ZipFile(io.BytesIO(payload))
    required = {"stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
    missing = required.difference(archive.namelist())
    if missing:
        raise ValueError(f"{feed_id}: file mancanti: {', '.join(sorted(missing))}")

    counts = {}
    counts["stops"] = copy_rows(cursor, "stops",
        ("feed_id","stop_id","stop_code","stop_name","stop_lat","stop_lon","wheelchair_boarding"),
        ((feed_id, r["stop_id"], r.get("stop_code"), r["stop_name"],
          float(r["stop_lat"]) if r.get("stop_lat") else None,
          float(r["stop_lon"]) if r.get("stop_lon") else None,
          integer(r.get("wheelchair_boarding"))) for r in csv_rows(archive, "stops.txt")))
    counts["routes"] = copy_rows(cursor, "routes",
        ("feed_id","route_id","route_short_name","route_long_name","route_type","route_color","route_text_color"),
        ((feed_id, r["route_id"], r.get("route_short_name"), r.get("route_long_name"),
          integer(r.get("route_type")), r.get("route_color"), r.get("route_text_color"))
         for r in csv_rows(archive, "routes.txt")))
    counts["trips"] = copy_rows(cursor, "trips",
        ("feed_id","route_id","service_id","trip_id","trip_headsign","trip_short_name","direction_id","wheelchair_accessible"),
        ((feed_id, r["route_id"], r["service_id"], r["trip_id"], r.get("trip_headsign"),
          r.get("trip_short_name"), integer(r.get("direction_id")), integer(r.get("wheelchair_accessible")))
         for r in csv_rows(archive, "trips.txt")))
    counts["stop_times"] = copy_rows(cursor, "stop_times",
        ("feed_id","trip_id","arrival_time","departure_time","stop_id","stop_sequence","pickup_type","drop_off_type"),
        ((feed_id, r["trip_id"], r["arrival_time"], r["departure_time"], r["stop_id"],
          int(r["stop_sequence"]), integer(r.get("pickup_type")), integer(r.get("drop_off_type")))
         for r in csv_rows(archive, "stop_times.txt")))

    calendars = list(csv_rows(archive, "calendar.txt") or [])
    if calendars:
        copy_rows(cursor, "calendars",
            ("feed_id","service_id","monday","tuesday","wednesday","thursday","friday","saturday","sunday","start_date","end_date"),
            ((feed_id, r["service_id"], *(integer(r[d]) for d in
              ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")),
              r["start_date"], r["end_date"]) for r in calendars))
    if "calendar_dates.txt" in archive.namelist():
        copy_rows(cursor, "calendar_dates", ("feed_id","service_id","date","exception_type"),
            ((feed_id, r["service_id"], r["date"], int(r["exception_type"]))
             for r in csv_rows(archive, "calendar_dates.txt")))

    start_date = min((r["start_date"] for r in calendars), default=None)
    end_date = max((r["end_date"] for r in calendars), default=None)
    cursor.execute("INSERT INTO feeds VALUES (%s,%s,%s,%s,%s,%s,%s)", (
        feed_id, url, datetime.now(timezone.utc), hashlib.sha256(payload).hexdigest(),
        start_date, end_date, "ok"))
    return counts


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL mancante: copia .env.example in .env e inserisci la connection string Supabase.")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    payloads = {}
    for feed_id, url in FEEDS.items():
        print(f"Scaricamento {feed_id}…", flush=True)
        payloads[feed_id] = download(url)
        (RAW_DIR / f"{feed_id}.zip").write_bytes(payloads[feed_id])

    # Un'unica transazione: se un feed fallisce, i dati precedenti rimangono intatti.
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA)
            cursor.execute("SET search_path TO gtfs, public")
            cursor.execute("TRUNCATE stop_times, trips, routes, stops, calendars, calendar_dates, feeds")
            for feed_id, url in FEEDS.items():
                counts = import_feed(cursor, feed_id, url, payloads[feed_id])
                print(f"  {feed_id}: {counts}", flush=True)
            cursor.execute("ANALYZE stops; ANALYZE stop_times; ANALYZE trips")
    print("Supabase aggiornato correttamente.")


if __name__ == "__main__":
    main()
