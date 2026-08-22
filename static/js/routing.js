window.routeStopsOnRoad = async function routeStopsOnRoad(stops) {
  const valid = stops.filter(stop => stop.stop_lat && stop.stop_lon);
  if (valid.length < 2) return valid.map(stop => [stop.stop_lat, stop.stop_lon]);
  const chunks = [];
  const size = 45;
  for (let start = 0; start < valid.length - 1; start += size - 1) {
    chunks.push(valid.slice(start, Math.min(start + size, valid.length)));
  }
  const result = [];
  for (const chunk of chunks) {
    const coordinates = chunk.map(stop => `${stop.stop_lon},${stop.stop_lat}`).join(";");
    const url = `https://router.project-osrm.org/route/v1/driving/${coordinates}?overview=full&geometries=geojson&continue_straight=true`;
    const response = await fetch(url);
    if (!response.ok) throw new Error("Routing non disponibile");
    const data = await response.json();
    if (data.code !== "Ok" || !data.routes?.[0]) throw new Error(data.code || "Nessun percorso");
    const points = data.routes[0].geometry.coordinates.map(([lon, lat]) => [lat, lon]);
    if (result.length) points.shift();
    result.push(...points);
  }
  return result;
};
