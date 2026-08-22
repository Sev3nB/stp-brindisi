(() => {
  const form = document.querySelector("#trip-form");
  if (!form) return;

  function setupAutocomplete(labelId, valueId) {
    const input = document.querySelector(labelId);
    const hidden = document.querySelector(valueId);
    const panel = input.parentElement.querySelector(".suggestions");
    let timer;
    const serviceNames = {
      brindisi: "Urbano Brindisi", extraurbano: "Extraurbano",
      ostuni: "Urbano Ostuni", francavilla: "Urbano Francavilla"
    };

    function selectStop(stop) {
      input.value = stop.stop_name;
      hidden.value = `${stop.feed_id}:${stop.stop_id}`;
      panel.hidden = true;
    }

    function showSuggestions(stops, nearby=false) {
      panel.replaceChildren();
      stops.forEach(stop => {
        const button = document.createElement("button");
        button.type = "button";
        button.role = "option";
        const name = document.createElement("strong");
        const service = document.createElement("small");
        name.textContent = stop.stop_name;
        const distance = nearby && stop.distance_m != null ? ` · ${stop.distance_m} m` : "";
        service.textContent = `${serviceNames[stop.feed_id] || stop.feed_id}${distance}`;
        button.append(name, service);
        button.addEventListener("click", () => selectStop(stop));
        panel.append(button);
      });
      panel.hidden = stops.length === 0;
    }

    input.addEventListener("input", () => {
      hidden.value = "";
      clearTimeout(timer);
      const query = input.value.trim();
      if (query.length < 2) { panel.hidden = true; return; }
      timer = setTimeout(async () => {
        try {
          const response = await fetch(`/api/stops?q=${encodeURIComponent(query)}&limit=50`);
          const stops = await response.json();
          showSuggestions(stops);
        } catch { panel.hidden = true; }
      }, 180);
    });
    document.addEventListener("click", event => {
      if (!input.parentElement.contains(event.target)) panel.hidden = true;
    });
    return { input, hidden, panel, showSuggestions, selectStop };
  }

  const from = setupAutocomplete("#from-label", "#from-stop");
  const to = setupAutocomplete("#to-label", "#to-stop");
  const params = new URLSearchParams(location.search);
  if (params.get("from_stop") && params.get("from_name")) {
    from.hidden.value = params.get("from_stop"); from.input.value = params.get("from_name");
  }
  if (params.get("to_stop") && params.get("to_name")) {
    to.hidden.value = params.get("to_stop"); to.input.value = params.get("to_name");
  }

  document.querySelector("#use-location")?.addEventListener("click", event => {
    const button = event.currentTarget;
    const error = document.querySelector("#form-error");
    if (!navigator.geolocation) { error.textContent = "Il browser non supporta la posizione."; return; }
    button.disabled = true; button.textContent = "Ricerca fermate vicine…"; error.textContent = "";
    navigator.geolocation.getCurrentPosition(async position => {
      try {
        const response = await fetch(`/api/nearby-stops?lat=${position.coords.latitude}&lon=${position.coords.longitude}`);
        if (!response.ok) throw new Error("Nearby API error");
        const stops = await response.json();
        from.input.value = ""; from.hidden.value = "";
        from.showSuggestions(stops, true);
        error.textContent = "Scegli una delle fermate più vicine alla tua posizione.";
      } catch {
        error.textContent = "Non sono riuscito a cercare le fermate vicine.";
      } finally {
        button.disabled = false; button.textContent = "◎ Usa la mia posizione";
      }
    }, () => {
      button.disabled = false; button.textContent = "◎ Usa la mia posizione";
      error.textContent = "Posizione non disponibile: controlla i permessi del browser.";
    }, { enableHighAccuracy: true, timeout: 12000 });
  });
  document.querySelector("#swap").addEventListener("click", () => {
    [from.input.value, to.input.value] = [to.input.value, from.input.value];
    [from.hidden.value, to.hidden.value] = [to.hidden.value, from.hidden.value];
  });
  form.addEventListener("submit", event => {
    const error = document.querySelector("#form-error");
    if (!from.hidden.value || !to.hidden.value) {
      event.preventDefault();
      error.textContent = "Seleziona entrambe le fermate dai suggerimenti.";
    } else if (from.hidden.value === to.hidden.value) {
      event.preventDefault();
      error.textContent = "Partenza e destinazione devono essere diverse.";
    }
  });
})();
