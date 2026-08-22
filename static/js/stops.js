(() => {
  const source = document.querySelector("#all-stops-data");
  const mapNode = document.querySelector("#stops-map");
  if (!source || !mapNode || typeof L === "undefined") return;
  const stops = JSON.parse(source.textContent).filter(stop => stop.stop_lat && stop.stop_lon);
  if (!stops.length) return;
  const map = L.map(mapNode);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap"
  }).addTo(map);
  const points = [];
  const seen = new Set();
  stops.forEach(stop => {
    const key = `${Number(stop.stop_lat).toFixed(5)}:${Number(stop.stop_lon).toFixed(5)}:${stop.stop_name}`;
    if (seen.has(key)) return;
    seen.add(key);
    const point = [stop.stop_lat, stop.stop_lon];
    points.push(point);
    L.circleMarker(point, {
      radius: 6, color: "#fff", weight: 2, fillColor: "#075985", fillOpacity: .9
    }).bindPopup(`<strong>${stop.stop_name}</strong><br><small>${stop.feed_id}</small><br><a href="/stop/${encodeURIComponent(stop.feed_id)}/${encodeURIComponent(stop.stop_id)}">Orari e linee →</a>`).addTo(map);
  });
  map.fitBounds(points, { padding: [24, 24], maxZoom: 15 });

  const placesLayer = L.layerGroup().addTo(map);
  function savedPlaces() { return window.STPStorage?.read("stpCustomPlaces", []) || []; }
  function savePlaces(places) { window.STPStorage?.write("stpCustomPlaces", places); }
  function renderPlaces() {
    placesLayer.clearLayers();
    savedPlaces().forEach(place => {
      L.marker([place.lat, place.lon], { title: place.name })
        .bindPopup(`<strong>${place.name}</strong><br><small>Luogo personale</small>`)
        .addTo(placesLayer);
    });
  }
  function savePlace(lat, lon, suggestedName="") {
    const name = window.prompt("Come vuoi chiamare questo luogo?", suggestedName);
    if (!name?.trim()) return;
    const places = savedPlaces();
    places.push({ id: String(Date.now()), name: name.trim(), lat, lon });
    savePlaces(places);
    renderPlaces();
  }
  renderPlaces();

  document.querySelector("#locate-me")?.addEventListener("click", () => {
    if (!navigator.geolocation) return window.alert("Geolocalizzazione non supportata.");
    navigator.geolocation.getCurrentPosition(position => {
      const { latitude: lat, longitude: lon } = position.coords;
      const marker = L.marker([lat, lon]).bindPopup("<strong>Posizione attuale</strong>").addTo(map).openPopup();
      map.setView([lat, lon], 16);
      if (window.confirm("Vuoi salvare questa posizione tra i tuoi luoghi?")) savePlace(lat, lon, "Casa");
      setTimeout(() => marker.remove(), 60000);
    }, () => window.alert("Non è stato possibile ottenere la posizione. Controlla i permessi del browser."), {
      enableHighAccuracy: true, timeout: 12000
    });
  });

  document.querySelector("#add-place")?.addEventListener("click", event => {
    event.currentTarget.classList.add("active");
    event.currentTarget.textContent = "Tocca un punto sulla mappa";
    map.once("click", click => {
      savePlace(click.latlng.lat, click.latlng.lng);
      event.currentTarget.classList.remove("active");
      event.currentTarget.textContent = "＋ Aggiungi luogo";
    });
  });

  document.querySelector("#manage-places")?.addEventListener("click", () => {
    const places = savedPlaces();
    if (!places.length) return window.alert("Non hai ancora salvato luoghi.");
    const list = places.map((place, index) => `${index + 1}. ${place.name}`).join("\n");
    const answer = window.prompt(`Luoghi salvati:\n${list}\n\nScrivi il numero da eliminare, oppure annulla.`);
    const index = Number(answer) - 1;
    if (Number.isInteger(index) && index >= 0 && index < places.length) {
      places.splice(index, 1); savePlaces(places); renderPlaces();
    }
  });
})();
