import { api } from "./api.js";

const TYPE_COLORS = {
  chess_club:     "#e63946",
  chess_bar:      "#f4a261",
  chess_meetup:   "#2a9d8f",
  chess_board:    "#457b9d",
  chess_shop:     "#6a4c93",
  chess_memorial: "#8d99ae",
  chess_museum:   "#e9c46a",
};

const TYPE_LABELS = {
  chess_club:     "Club",
  chess_bar:      "Bar",
  chess_meetup:   "Meetup",
  chess_board:    "Board",
  chess_shop:     "Shop",
  chess_memorial: "Memorial",
  chess_museum:   "Museum",
};

let map, markerLayer, allPlaces = [];

export function initMap(containerId = "map") {
  map = L.map(containerId, { zoomControl: true }).setView([20, 0], 2);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "© OpenStreetMap © CARTO",
    maxZoom: 19,
  }).addTo(map);

  markerLayer = L.markerClusterGroup({
    showCoverageOnHover: false,
    maxClusterRadius: 5,
    iconCreateFunction: (cluster) => {
      const count = cluster.getChildCount();
      return L.divIcon({
        html: `<div class="cluster-icon">${count}</div>`,
        className: "",
        iconSize: [36, 36],
      });
    },
  });

  map.addLayer(markerLayer);
}

function makeIcon(type, verified) {
  const color = TYPE_COLORS[type] || "#555";
  const opacity = verified ? 1 : 0.55;
  return L.divIcon({
    html: `<div class="map-pin" style="background:${color};opacity:${opacity}" title="${TYPE_LABELS[type] || type}"></div>`,
    className: "",
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

export async function loadPlaces(params = {}) {
  allPlaces = await api.places.list(params);
  renderMarkers(allPlaces);
  return allPlaces;
}

export function renderMarkers(places) {
  markerLayer.clearLayers();
  places.forEach((p, i) => {
    if (!p.lat || !p.lng) return;
    const marker = L.marker([p.lat, p.lng], { icon: makeIcon(p.type, p.verified) });
    marker.bindPopup(buildPopup(p), { maxWidth: 280 });
    // Stagger animation
    setTimeout(() => markerLayer.addLayer(marker), i * 8);
  });
}

function buildPopup(p) {
  const verifiedBadge = p.verified
    ? `<span class="badge verified">✓ Verified</span>`
    : `<span class="badge unverified">Unverified</span>`;
  const typeLabel = TYPE_LABELS[p.type] || p.type || "";
  return `
    <div class="popup-card">
      <div class="popup-header">
        <span class="popup-type">${typeLabel}</span>
        ${verifiedBadge}
      </div>
      <h3 class="popup-name">${p.name}</h3>
      <p class="popup-location">${p.city}, ${p.country}</p>
      ${p.description ? `<p class="popup-desc">${p.description}</p>` : ""}
      ${p.schedule_notes ? `<p class="popup-schedule">🕒 ${p.schedule_notes}</p>` : ""}
      ${p.website ? `<a href="${p.website}" target="_blank" class="popup-link">Visit website →</a>` : ""}
    </div>
  `;
}

export function filterMarkers(places) {
  renderMarkers(places);
}

export function flyTo(lat, lng, zoom = 13) {
  map.flyTo([lat, lng], zoom, { duration: 1.2 });
}
