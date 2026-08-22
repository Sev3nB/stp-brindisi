(() => {
  const source = document.querySelector("#variants-data");
  const mapNode = document.querySelector("#route-map");
  if (!source || !mapNode || typeof L === "undefined") return;
  const variants = JSON.parse(source.textContent);
  const map = L.map(mapNode, { scrollWheelZoom: false });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap"
  }).addTo(map);
  let layer;
  let renderToken = 0;

  async function showVariant(index) {
    const token = ++renderToken;
    if (layer) layer.remove();
    layer = L.layerGroup().addTo(map);
    const stops = variants[index].stops.filter(stop => stop.stop_lat && stop.stop_lon);
    const points = stops.map(stop => [stop.stop_lat, stop.stop_lon]);
    if (points.length) {
      const fallbackLine = L.polyline(points, { color: "#94a3b8", weight: 4, opacity: .7, dashArray: "7 8" }).addTo(layer);
      stops.forEach((stop, stopIndex) => {
        L.circleMarker([stop.stop_lat, stop.stop_lon], {
          radius: stopIndex === 0 || stopIndex === stops.length - 1 ? 7 : 4,
          color: "#fff", weight: 2, fillColor: "#075985", fillOpacity: 1
        }).bindPopup(`<strong>${stopIndex + 1}. ${stop.stop_name}</strong>`).addTo(layer);
      });
      map.fitBounds(points, { padding: [28, 28] });
      try {
        const roadPoints = await window.routeStopsOnRoad(stops);
        if (token === renderToken && layer && roadPoints.length) {
          fallbackLine.remove();
          L.polyline(roadPoints, { color: "#0284c7", weight: 5, opacity: .86 }).addTo(layer);
        }
      } catch (error) {
        console.info("Percorso stradale non disponibile, uso collegamento fermate", error);
      }
    }
    document.querySelectorAll("[data-variant]").forEach((button, i) => button.classList.toggle("active", i === index));
    document.querySelectorAll("[data-panel]").forEach((panel, i) => panel.classList.toggle("hidden", i !== index));
    setTimeout(() => map.invalidateSize(), 0);
  }
  document.querySelectorAll("[data-variant]").forEach((button, index) => button.addEventListener("click", () => showVariant(index)));
  showVariant(0);
})();
