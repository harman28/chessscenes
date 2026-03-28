import { api } from "./api.js";

const TYPE_LABELS = {
  chess_club: "Chess Club", chess_bar: "Chess Bar", chess_meetup: "Chess Meetup",
  chess_board: "Outdoor Board", chess_shop: "Chess Shop",
  chess_memorial: "Chess Memorial", chess_museum: "Chess Museum",
};
const TYPE_COLORS = {
  chess_club: "#e63946", chess_bar: "#f4a261", chess_meetup: "#2a9d8f",
  chess_board: "#457b9d", chess_shop: "#6a4c93", chess_memorial: "#8d99ae", chess_museum: "#e9c46a",
};
const DAY_LABELS = { mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun" };
const TODAY_SHORT = ["sun","mon","tue","wed","thu","fri","sat"][new Date().getDay()];
const DAY_NAME_RE = /^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(,\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday))*\.?$/i;

const slug = window.location.hash.slice(1);
const el = document.getElementById("place-detail");

// Smart back button — goes back in history if possible, otherwise map
document.getElementById("back-btn").addEventListener("click", () => {
  if (history.length > 1) history.back();
  else location.href = "index.html";
});

if (!slug) {
  el.innerHTML = '<p class="place-error">No place specified.</p>';
} else {
  api.places.get(slug)
    .then(render)
    .catch(() => { el.innerHTML = '<p class="place-error">Place not found.</p>'; });
}

function render(p) {
  document.title = `${p.name} — Chess Scenes`;

  const color = TYPE_COLORS[p.type] || "#555";
  const label = TYPE_LABELS[p.type] || p.type || "";
  const days = p.schedule_days
    ? p.schedule_days.split(",").map(d => d.trim()).filter(d => DAY_LABELS[d])
    : [];
  // Don't show schedule_notes if it's just a list of day names (redundant with pills)
  const showNotes = p.schedule_notes && !DAY_NAME_RE.test(p.schedule_notes.trim());

  el.innerHTML = `
    ${p.image_url
      ? `<img src="${p.image_url}" alt="${p.name}" class="place-hero-img">`
      : `<div class="place-hero-placeholder" style="background:${color}"><span>♟</span></div>`}
    <div class="place-layout">
      <div class="place-content">
        <div class="place-meta">
          <span class="place-type-tag" style="background:${color}">${label}</span>
          ${!p.verified ? `<span class="place-unverified">⏳ Unverified</span>` : ""}
        </div>
        <div class="place-city">${p.city}${p.country ? `, ${p.country}` : ""}</div>
        <h1 class="place-name">${p.name}</h1>
        ${p.description ? `<p class="place-desc">${p.description}</p>` : ""}
        ${days.length ? `<div class="place-days">${days.map(d => `<span class="place-day${d === TODAY_SHORT ? " place-day-today" : ""}">${DAY_LABELS[d]}</span>`).join("")}</div>` : ""}
        ${showNotes ? `<p class="place-schedule-notes">🕒 ${p.schedule_notes}</p>` : ""}
        <div class="place-actions">
          ${p.website ? `<a href="${p.website}" target="_blank" class="btn btn-ink">Website ↗</a>` : ""}
          ${p.maps_url ? `<a href="${p.maps_url}" target="_blank" class="btn btn-border">Google Maps ↗</a>` : ""}
          <button class="btn btn-border" id="share-btn">🔗 Share</button>
        </div>
      </div>
      ${p.lat && p.lng ? `<div class="place-map-col"><div id="place-map"></div></div>` : ""}
    </div>
  `;

  document.getElementById("share-btn").addEventListener("click", function () {
    navigator.clipboard.writeText(location.href).then(() => {
      this.textContent = "Copied!";
      setTimeout(() => { this.textContent = "🔗 Share"; }, 2000);
    });
  });

  if (p.lat && p.lng) initMap(p);
}

const TYPE_ICONS = {
  chess_club: "♜", chess_bar: "♟", chess_meetup: "♝",
  chess_board: "♞", chess_shop: "♛", chess_memorial: "♔", chess_museum: "♕",
};

function initMap(p) {
  const color = TYPE_COLORS[p.type] || "#555";
  const icon = TYPE_ICONS[p.type] || "♟";
  const m = L.map("place-map", { zoomControl: true, scrollWheelZoom: false })
    .setView([p.lat, p.lng], 15);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "© OpenStreetMap © CARTO", maxZoom: 19,
  }).addTo(m);
  L.marker([p.lat, p.lng], {
    icon: L.divIcon({
      className: "",
      html: `<div class="custom-marker" style="background:${color}"><span>${icon}</span></div>`,
      iconSize: [30, 30], iconAnchor: [15, 30], popupAnchor: [0, -32],
    })
  }).addTo(m);
}
