(() => {
  const read = (key, fallback) => {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  };
  const write = (key, value) => localStorage.setItem(key, JSON.stringify(value));
  const plannerUrl = (side, item) => {
    const params = new URLSearchParams({ [`${side}_stop`]: item.key, [`${side}_name`]: item.name });
    if (Number.isFinite(Number(item.lat)) && Number.isFinite(Number(item.lon))) {
      params.set(`${side}_lat`, item.lat); params.set(`${side}_lon`, item.lon);
    }
    return `/?${params.toString()}#planner`;
  };

  const themeButton = document.querySelector("#theme-toggle");
  const updateThemeIcon = () => {
    const icon = themeButton?.querySelector("span");
    if (icon) icon.textContent = document.documentElement.dataset.theme === "dark" ? "☀" : "◐";
  };
  themeButton?.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("stpTheme", theme);
    updateThemeIcon();
  });
  updateThemeIcon();

  function toggleFavorite(type, item) {
    const key = `stpFavorite${type}`;
    const items = read(key, []);
    const index = items.findIndex(saved => saved.key === item.key);
    if (index >= 0) items.splice(index, 1); else items.push(item);
    write(key, items);
    refreshAll();
  }

  function refreshButtons() {
    const lines = read("stpFavoriteLines", []);
    const stops = read("stpFavoriteStops", []);
    document.querySelectorAll("[data-favorite-line]").forEach(button => {
      const active = lines.some(item => item.key === button.dataset.key);
      button.classList.toggle("active", active);
      button.textContent = active ? "★ Preferita" : "☆ Preferito";
    });
    document.querySelectorAll("[data-favorite-stop]").forEach(button => {
      const active = stops.some(item => item.key === button.dataset.key);
      button.classList.toggle("active", active);
      button.textContent = button.classList.contains("labeled")
        ? (active ? "★ Salvata" : "☆ Salva")
        : (active ? "★" : "☆");
      button.setAttribute("aria-pressed", String(active));
      button.setAttribute("aria-label", active ? "Rimuovi fermata dai preferiti" : "Salva fermata nei preferiti");
    });
  }

  function stopFavoriteCard(item) {
    const card = document.createElement("article");
    card.className = "favorite-item";
    const title = document.createElement("strong");
    title.textContent = item.name;
    const actions = document.createElement("div");
    const from = document.createElement("a");
    from.href = plannerUrl("from", item); from.textContent = "Parti da qui";
    const to = document.createElement("a");
    to.href = plannerUrl("to", item); to.textContent = "Arriva qui";
    actions.append(from, to); card.append(title, actions);
    return card;
  }

  function lineFavoriteCard(item) {
    const link = document.createElement("a");
    link.className = "favorite-item favorite-line-link";
    link.href = item.url;
    const title = document.createElement("strong"); title.textContent = item.name;
    const hint = document.createElement("small"); hint.textContent = "Apri percorso e orari →";
    link.append(title, hint); return link;
  }

  function renderFavorites(container, compact=false) {
    if (!container) return 0;
    const lines = read("stpFavoriteLines", []);
    const stops = read("stpFavoriteStops", []);
    container.replaceChildren();
    if (!lines.length && !stops.length) {
      const empty = document.createElement("p");
      empty.className = "favorites-empty";
      empty.textContent = "Aggiungi una linea o una fermata con la stella per ritrovarla qui.";
      container.append(empty); return 0;
    }
    lines.forEach(item => container.append(lineFavoriteCard(item)));
    stops.forEach(item => container.append(stopFavoriteCard(item)));
    if (compact) container.classList.add("compact-favorites");
    return lines.length + stops.length;
  }

  function renderHomeFavorites() {
    const section = document.querySelector("#favorites-home");
    const container = document.querySelector("#favorite-links");
    if (!section || !container) return;
    section.hidden = renderFavorites(container, true) === 0;
  }

  function renderSheet() { renderFavorites(document.querySelector("#favorites-content")); }
  function refreshAll() { refreshButtons(); renderHomeFavorites(); renderSheet(); }

  document.querySelectorAll("[data-favorite-line]").forEach(button => button.addEventListener("click", () => {
    toggleFavorite("Lines", { key: button.dataset.key, name: button.dataset.name, url: button.dataset.url });
  }));
  document.querySelectorAll("[data-favorite-stop]").forEach(button => button.addEventListener("click", () => {
    toggleFavorite("Stops", {
      key: button.dataset.key, name: button.dataset.name,
      lat: Number(button.dataset.lat), lon: Number(button.dataset.lon)
    });
  }));

  const sheet = document.querySelector("#favorites-sheet");
  const backdrop = document.querySelector("#favorites-backdrop");
  const openSheet = () => {
    renderSheet(); sheet?.classList.add("open"); sheet?.setAttribute("aria-hidden", "false");
    if (backdrop) backdrop.hidden = false;
  };
  const closeSheet = () => {
    sheet?.classList.remove("open"); sheet?.setAttribute("aria-hidden", "true");
    if (backdrop) backdrop.hidden = true;
  };
  document.querySelector("#favorites-toggle")?.addEventListener("click", openSheet);
  document.querySelector("#favorites-close")?.addEventListener("click", closeSheet);
  backdrop?.addEventListener("click", closeSheet);
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeSheet(); });

  refreshAll();
  window.STPStorage = { read, write };
})();
