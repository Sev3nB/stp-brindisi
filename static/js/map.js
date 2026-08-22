(() => {
  const node = document.querySelector("#stops-data");
  if (!node || typeof L === "undefined") return;
  const stops = JSON.parse(node.textContent).filter(s => s.stop_lat && s.stop_lon);
  if (!stops.length) { document.querySelector("#map").remove(); return; }
  const map = L.map("map", { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap"
  }).addTo(map);
  const points = stops.map(s => [s.stop_lat, s.stop_lon]);
  const fallbackLine = L.polyline(points, { color: "#94a3b8", weight: 4, opacity: .7, dashArray: "7 8" }).addTo(map);
  stops.forEach((stop, index) => {
    L.circleMarker([stop.stop_lat, stop.stop_lon], {
      radius: index === 0 || index === stops.length - 1 ? 7 : 4,
      color: "#fff", weight: 2, fillColor: "#075985", fillOpacity: 1
    }).bindPopup(`<strong>${stop.time_display}</strong><br>${stop.stop_name}`).addTo(map);
  });
  map.fitBounds(points, { padding: [28, 28] });
  if (window.routeStopsOnRoad) {
    window.routeStopsOnRoad(stops).then(roadPoints => {
      if (!roadPoints.length) return;
      fallbackLine.remove();
      L.polyline(roadPoints, { color: "#0284c7", weight: 5, opacity: .86 }).addTo(map);
    }).catch(error => console.info("Percorso stradale non disponibile", error));
  }
})();
