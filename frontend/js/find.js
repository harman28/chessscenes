import { api } from "./api.js";

// ── Constants ──────────────────────────────────────────────────────────────────

const DAY_ABBR = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];

const TYPE_LABEL = {
  chess_club:     "Chess club",
  chess_meetup:   "Chess meetup",
  chess_bar:      "Chess bar",
  chess_shop:     "Chess shop",
  chess_board:    "Public board",
  chess_museum:   "Museum",
  chess_memorial: "Memorial",
};

// Display order for place type groups
const TYPE_GROUPS = [
  { label: "Clubs & meetups",   types: ["chess_club", "chess_meetup"] },
  { label: "Chess bars",        types: ["chess_bar"] },
  { label: "Chess shops",       types: ["chess_shop"] },
  { label: "Public boards",     types: ["chess_board"] },
  { label: "Museums & memorials", types: ["chess_museum", "chess_memorial"] },
];

// ── DOM ────────────────────────────────────────────────────────────────────────

const form       = document.getElementById("find-form");
const cityInput  = document.getElementById("find-city");
const dateInput  = document.getElementById("find-date");
const resultsEl  = document.getElementById("find-results");

// ── Search ─────────────────────────────────────────────────────────────────────

form.addEventListener("submit", (e) => { e.preventDefault(); runSearch(); });

// Pre-fill from URL params (e.g. ?city=Berlin&date=2025-04-12)
const params = new URLSearchParams(location.search);
if (params.get("city")) {
  cityInput.value = params.get("city");
  if (params.get("date")) dateInput.value = params.get("date");
  runSearch();
}

async function runSearch() {
  const city = cityInput.value.trim();
  const date = dateInput.value; // ISO: YYYY-MM-DD

  if (!city) { cityInput.focus(); return; }

  // Update URL without reloading so the search is shareable
  const qs = new URLSearchParams({ city, ...(date ? { date } : {}) });
  history.replaceState(null, "", "?" + qs);

  resultsEl.innerHTML = `<div class="find-loading">Finding chess in ${esc(city)}\u2026</div>`;

  try {
    const [places, events] = await Promise.all([
      api.places.list({ city }),
      api.events.list({ city, ...(date ? { date } : {}) }),
    ]);
    render(city, date, places, events);
  } catch (err) {
    resultsEl.innerHTML = `<div class="find-error">Something went wrong — ${esc(err.message)}</div>`;
  }
}

// ── Render ─────────────────────────────────────────────────────────────────────

function render(city, date, places, events) {
  const dateObj = date ? new Date(date + "T00:00:00") : null;
  const dateLabel = dateObj
    ? dateObj.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
    : null;
  const selectedDay = dateObj ? DAY_ABBR[dateObj.getDay()] : null;
  const dowLabel = dateObj
    ? dateObj.toLocaleDateString("en-GB", { weekday: "long" })
    : null;

  const sections = [];

  // ── Section 1: Events ──
  if (events.length) {
    const heading = dateLabel ? `Events on ${dateLabel}` : "Upcoming events";
    sections.push(section(heading, events.map(eventCard)));
  }

  // ── Section 2: Places that meet on the selected day ──
  let remaining = places;

  if (selectedDay) {
    const meetsToday = places.filter(p => meetsDayOf(p, selectedDay));
    remaining = places.filter(p => !meetsDayOf(p, selectedDay));

    if (meetsToday.length) {
      sections.push(section(`Open on ${dowLabel}`, meetsToday.map(p => placeCard(p, true))));
    }
  }

  // ── Section 3: Remaining places, grouped by type ──
  const knownTypes = TYPE_GROUPS.flatMap(g => g.types);

  for (const group of TYPE_GROUPS) {
    const grouped = remaining.filter(p => group.types.includes(p.type));
    if (grouped.length) sections.push(section(group.label, grouped.map(p => placeCard(p, false))));
  }

  const unknown = remaining.filter(p => !knownTypes.includes(p.type));
  if (unknown.length) sections.push(section("Other", unknown.map(p => placeCard(p, false))));

  // ── Empty state ──
  if (!sections.length) {
    resultsEl.innerHTML = `
      <div class="find-empty">
        <p>No chess found in <strong>${esc(city)}</strong>${dateLabel ? ` on ${dateLabel}` : ""}.</p>
        <p>Know a place? <a href="index.html#suggest">Suggest it →</a></p>
      </div>`;
    return;
  }

  const summaryLine = dateLabel ? `${city} · ${dateLabel}` : city;
  resultsEl.innerHTML = `
    <p class="find-summary">${esc(summaryLine)}</p>
    ${sections.join("")}
  `;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function section(heading, cards) {
  return `
    <section class="result-section">
      <h2 class="section-heading">
        ${esc(heading)}
        <span class="section-count">${cards.length}</span>
      </h2>
      <div class="card-grid">${cards.join("")}</div>
    </section>
  `;
}

function meetsDayOf(place, dayAbbr) {
  if (!place.schedule_days) return false;
  return place.schedule_days.split(",").map(s => s.trim().toLowerCase()).includes(dayAbbr);
}

function placeCard(p, meetsToday) {
  const typeLabel = TYPE_LABEL[p.type] || p.type.replace("chess_", "").replace(/_/g, " ");
  const extraClass = meetsToday ? " find-card--meets-today" : "";

  const badges = [];
  if (meetsToday) badges.push(`<span class="find-card-badge badge-today">Meets today</span>`);
  if (p.verified)  badges.push(`<span class="find-card-badge badge-verified">Verified</span>`);

  return `
    <div class="find-card${extraClass}">
      <div class="find-card-top">
        <span class="find-card-type">${esc(typeLabel)}</span>
        ${badges.length ? `<div class="find-card-badges">${badges.join("")}</div>` : ""}
      </div>
      <h3 class="find-card-name">${esc(p.name)}</h3>
      ${p.schedule_notes ? `<p class="find-card-meta">${esc(p.schedule_notes)}</p>` : ""}
      ${p.description   ? `<p class="find-card-desc">${esc(p.description)}</p>` : ""}
      ${p.website       ? `<a class="find-card-link" href="${safeUrl(p.website)}" target="_blank" rel="noopener">Website →</a>` : ""}
    </div>
  `;
}

function eventCard(e) {
  const dateStr = new Date(e.event_date + "T00:00:00").toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short",
  });
  const timeStr = e.event_time ? ` · ${e.event_time}` : "";

  return `
    <div class="find-card find-card--event">
      <div class="find-card-top">
        <span class="find-card-type">Event</span>
        <span class="find-card-badge badge-date">${esc(dateStr + timeStr)}</span>
      </div>
      <h3 class="find-card-name">${esc(e.name)}</h3>
      ${e.place_name  ? `<p class="find-card-venue">@ ${esc(e.place_name)}</p>` : ""}
      ${e.description ? `<p class="find-card-desc">${esc(e.description)}</p>` : ""}
      ${e.url         ? `<a class="find-card-link" href="${safeUrl(e.url)}" target="_blank" rel="noopener">Details →</a>` : ""}
    </div>
  `;
}

function safeUrl(url) {
  try {
    const u = new URL(url);
    return (u.protocol === "http:" || u.protocol === "https:") ? url : "#";
  } catch { return "#"; }
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
