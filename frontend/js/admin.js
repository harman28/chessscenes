import { api, token } from "./api.js";

// ── Auth gate ─────────────────────────────────────────────────────────────────

if (!token.get()) showLoginScreen();
else initDashboard();

function showLoginScreen() {
  document.getElementById("login-screen").classList.remove("hidden");
  document.getElementById("dashboard").classList.add("hidden");
  document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value;
    const password = document.getElementById("login-password").value;
    try {
      const res = await api.auth.login(username, password);
      token.set(res.token);
      location.reload();
    } catch (err) {
      document.getElementById("login-error").textContent = err.message;
    }
  });
}

async function initDashboard() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("dashboard").classList.remove("hidden");
  document.getElementById("logout-btn").addEventListener("click", () => {
    token.clear();
    location.reload();
  });

  setupTabs();
  await Promise.all([loadSuggestions(), loadPlaces(), loadEvents(), loadSettings()]);
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });

  // Suggestion status filter buttons
  document.querySelectorAll(".suggestion-filter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".suggestion-filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      loadSuggestions(btn.dataset.status);
    });
  });
}

// ── Suggestions ───────────────────────────────────────────────────────────────

async function loadSuggestions(status = "pending") {
  const el = document.getElementById("suggestions-list");
  el.innerHTML = "<p>Loading…</p>";
  const items = await api.admin.suggestions.list(status);
  if (!items.length) { el.innerHTML = `<p class="empty">No ${status} suggestions.</p>`; return; }
  el.innerHTML = items.map(suggestionRow).join("");
  el.querySelectorAll(".approve-btn").forEach(btn =>
    btn.addEventListener("click", () => approveSuggestion(+btn.dataset.id)));
  el.querySelectorAll(".reject-btn").forEach(btn =>
    btn.addEventListener("click", () => rejectSuggestion(+btn.dataset.id)));
}

function suggestionRow(s) {
  return `
    <div class="suggestion-row" data-id="${s.id}">
      <div class="suggestion-info">
        <strong>${s.name}</strong> — ${s.city}, ${s.country}
        ${s.type ? `<span class="tag">${s.type}</span>` : ""}
        ${s.website ? `<a href="${s.website}" target="_blank">↗</a>` : ""}
        ${s.description ? `<p class="suggestion-desc">${s.description}</p>` : ""}
        ${s.schedule_notes ? `<p class="schedule-note">🕒 ${s.schedule_notes}</p>` : ""}
        <small>By ${s.submitter_name || "anonymous"} · ${formatDate(s.submitted_at)}</small>
      </div>
      <div class="suggestion-actions">
        <button class="btn btn-green approve-btn" data-id="${s.id}">Approve</button>
        <button class="btn btn-red reject-btn" data-id="${s.id}">Reject</button>
      </div>
    </div>`;
}

async function approveSuggestion(id) {
  await api.admin.suggestions.approve(id);
  await loadSuggestions();
  await loadPlaces();
}

async function rejectSuggestion(id) {
  const notes = prompt("Rejection notes (optional):");
  await api.admin.suggestions.reject(id, notes || "");
  await loadSuggestions();
}

// ── Places ────────────────────────────────────────────────────────────────────

let allPlaces = [];

async function loadPlaces() {
  const el = document.getElementById("places-list");
  el.innerHTML = "<p>Loading…</p>";
  allPlaces = await api.admin.places.list();
  renderPlaces(allPlaces);
  populatePlaceSelect();
}

function renderPlaces(places) {
  const el = document.getElementById("places-list");
  if (!places.length) { el.innerHTML = `<p class="empty">No places yet.</p>`; return; }
  el.innerHTML = `
    <table class="admin-table">
      <thead><tr>
        <th>Name</th><th>City</th><th>Type</th>
        <th>Verified</th><th>Active</th><th>Actions</th>
      </tr></thead>
      <tbody>
        ${places.map(placeRow).join("")}
      </tbody>
    </table>`;
  el.querySelectorAll(".toggle-active-btn").forEach(btn =>
    btn.addEventListener("click", async () => {
      await api.admin.places.toggleActive(+btn.dataset.id);
      await loadPlaces();
    }));
  el.querySelectorAll(".toggle-verified-btn").forEach(btn =>
    btn.addEventListener("click", async () => {
      await api.admin.places.toggleVerified(+btn.dataset.id);
      await loadPlaces();
    }));
  el.querySelectorAll(".edit-place-btn").forEach(btn =>
    btn.addEventListener("click", () => openPlaceForm(+btn.dataset.id)));
  el.querySelectorAll(".delete-place-btn").forEach(btn =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this place?")) return;
      await api.admin.places.delete(+btn.dataset.id);
      await loadPlaces();
    }));
}

function placeRow(p) {
  return `
    <tr class="${!p.active ? "row-inactive" : ""}">
      <td>${p.name}</td>
      <td>${p.city}, ${p.country}</td>
      <td><span class="tag">${p.type || "—"}</span></td>
      <td><button class="toggle-verified-btn pill ${p.verified ? "on" : "off"}" data-id="${p.id}">${p.verified ? "✓" : "✗"}</button></td>
      <td><button class="toggle-active-btn pill ${p.active ? "on" : "off"}" data-id="${p.id}">${p.active ? "On" : "Off"}</button></td>
      <td class="row-actions">
        <button class="btn btn-small edit-place-btn" data-id="${p.id}">Edit</button>
        <button class="btn btn-small btn-red delete-place-btn" data-id="${p.id}">Delete</button>
      </td>
    </tr>`;
}

document.getElementById("places-search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  renderPlaces(allPlaces.filter(p =>
    p.name.toLowerCase().includes(q) || p.city.toLowerCase().includes(q)
  ));
});

// Place form (add / edit)
document.getElementById("add-place-btn").addEventListener("click", () => openPlaceForm());

let pinMap = null, pinMarker = null;

function initPinMap() {
  if (pinMap) return;
  pinMap = L.map("place-pin-map").setView([20, 0], 2);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "© OpenStreetMap © CARTO", maxZoom: 19,
  }).addTo(pinMap);
  pinMap.on("click", (e) => {
    const { lat, lng } = e.latlng;
    setPin(lat, lng);
    const f = document.getElementById("place-form");
    f.elements.lat.value = lat.toFixed(6);
    f.elements.lng.value = lng.toFixed(6);
  });
}

function setPin(lat, lng) {
  if (pinMarker) pinMarker.remove();
  pinMarker = L.marker([lat, lng]).addTo(pinMap);
}

function openPlaceForm(id = null) {
  const place = id ? allPlaces.find(p => p.id === id) : null;
  fillPlaceForm(place);
  document.getElementById("place-form-modal").classList.remove("hidden");
  setTimeout(() => {
    initPinMap();
    pinMap.invalidateSize();
    if (place?.lat && place?.lng) {
      setPin(place.lat, place.lng);
      pinMap.setView([place.lat, place.lng], 13);
    } else {
      if (pinMarker) { pinMarker.remove(); pinMarker = null; }
      pinMap.setView([20, 0], 2);
    }
  }, 50);
}

function fillPlaceForm(place) {
  const f = document.getElementById("place-form");
  f.reset();
  document.getElementById("place-form-id").value = place?.id || "";
  ["name","city","country","lat","lng","type","description",
   "schedule_notes","website","image_url"].forEach(field => {
    const el = f.elements[field];
    if (el) el.value = place?.[field] ?? "";
  });
  const activeDays = (place?.schedule_days || "").split(",").map(d => d.trim()).filter(Boolean);
  ["mon","tue","wed","thu","fri","sat","sun"].forEach(day => {
    const cb = f.elements[`day_${day}`];
    if (cb) cb.checked = activeDays.includes(day);
  });
  if (f.elements.verified) f.elements.verified.checked = place?.verified ?? true;
  if (f.elements.active)   f.elements.active.checked   = place?.active   ?? true;
  document.getElementById("place-form-title").textContent = place ? "Edit Place" : "Add Place";
}

document.getElementById("place-form-modal").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) e.currentTarget.classList.add("hidden");
});

document.getElementById("place-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const id = document.getElementById("place-form-id").value;
  const data = {
    name:           f.elements.name.value,
    city:           f.elements.city.value,
    country:        f.elements.country.value,
    lat:            parseFloat(f.elements.lat.value) || null,
    lng:            parseFloat(f.elements.lng.value) || null,
    type:           f.elements.type.value,
    description:    f.elements.description.value,
    schedule_notes: f.elements.schedule_notes.value,
    schedule_days:  ["mon","tue","wed","thu","fri","sat","sun"]
      .filter(d => f.elements[`day_${d}`]?.checked).join(","),
    website:        f.elements.website.value,
    image_url:      f.elements.image_url.value,
    verified:       f.elements.verified.checked,
    active:         f.elements.active.checked,
  };
  if (id) {
    await api.admin.places.update(+id, data);
  } else {
    await api.admin.places.create(data);
  }
  document.getElementById("place-form-modal").classList.add("hidden");
  await loadPlaces();
});

// ── LLM-assisted entry ────────────────────────────────────────────────────────

document.getElementById("llm-parse-btn").addEventListener("click", runLLMParse);

async function runLLMParse() {
  const text = document.getElementById("llm-input").value.trim();
  const imgFile = document.getElementById("llm-image").files[0];

  if (!text && !imgFile) {
    alert("Paste some text or upload a screenshot first.");
    return;
  }

  const statusEl = document.getElementById("llm-status");
  statusEl.textContent = "Parsing with Claude…";

  try {
    let imageBase64 = null, imageMediaType = null;
    if (imgFile) {
      imageBase64 = await fileToBase64(imgFile);
      imageMediaType = imgFile.type;
    }

    const parsed = await api.admin.llm.parse(text, imageBase64, imageMediaType);

    // Pre-fill the place form
    openPlaceForm();
    const f = document.getElementById("place-form");
    Object.entries(parsed).forEach(([k, v]) => {
      if (k === "schedule_days") {
        const days = (v || "").split(",").map(d => d.trim()).filter(Boolean);
        ["mon","tue","wed","thu","fri","sat","sun"].forEach(day => {
          const cb = f.elements[`day_${day}`];
          if (cb) cb.checked = days.includes(day);
        });
      } else {
        const el = f.elements[k];
        if (el && v !== null && v !== undefined) el.value = v;
      }
    });
    if (parsed.lat && parsed.lng) {
      setTimeout(() => { setPin(parsed.lat, parsed.lng); pinMap?.setView([parsed.lat, parsed.lng], 13); }, 100);
    }

    statusEl.textContent = "✓ Form pre-filled — review and save.";
    document.getElementById("llm-input").value = "";
    document.getElementById("llm-image").value = "";
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
    console.error(err);
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

// ── Events ────────────────────────────────────────────────────────────────────

async function loadEvents() {
  const el = document.getElementById("events-list");
  el.innerHTML = "<p>Loading…</p>";
  const events = await api.admin.events.list();
  if (!events.length) { el.innerHTML = `<p class="empty">No events yet.</p>`; return; }
  el.innerHTML = `
    <table class="admin-table">
      <thead><tr><th>Name</th><th>Date</th><th>City</th><th>Venue</th><th>Actions</th></tr></thead>
      <tbody>${events.map(eventRow).join("")}</tbody>
    </table>`;
  el.querySelectorAll(".delete-event-btn").forEach(btn =>
    btn.addEventListener("click", async () => {
      if (!confirm("Delete this event?")) return;
      await api.admin.events.delete(+btn.dataset.id);
      await loadEvents();
    }));
}

function eventRow(e) {
  return `
    <tr>
      <td>${e.name}</td>
      <td>${e.event_date}${e.event_time ? " " + e.event_time : ""}</td>
      <td>${e.city}, ${e.country}</td>
      <td>${e.place_name || "—"}</td>
      <td><button class="btn btn-small btn-red delete-event-btn" data-id="${e.id}">Delete</button></td>
    </tr>`;
}

document.getElementById("event-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  await api.admin.events.create({
    place_id:    f.elements.place_id.value ? +f.elements.place_id.value : null,
    name:        f.elements.name.value,
    city:        f.elements.city.value,
    country:     f.elements.country.value,
    lat:         parseFloat(f.elements.lat.value) || null,
    lng:         parseFloat(f.elements.lng.value) || null,
    event_date:  f.elements.event_date.value,
    event_time:  f.elements.event_time.value || null,
    description: f.elements.description.value,
    url:         f.elements.url.value,
  });
  f.reset();
  await loadEvents();
});

function populatePlaceSelect() {
  const sel = document.getElementById("event-place-select");
  sel.innerHTML = `<option value="">— No linked place —</option>` +
    allPlaces.map(p => `<option value="${p.id}">${p.name} (${p.city})</option>`).join("");
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function loadSettings() {
  const settings = await api.admin.settings.get();
  const showUnverified = document.getElementById("setting-show-unverified");
  if (showUnverified) showUnverified.checked = settings.show_unverified === "true";
}

document.getElementById("settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const showUnverified = document.getElementById("setting-show-unverified").checked;
  await api.admin.settings.update({ show_unverified: String(showUnverified) });
  document.getElementById("settings-saved").textContent = "Saved ✓";
  setTimeout(() => document.getElementById("settings-saved").textContent = "", 2000);
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso) {
  return iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—";
}
