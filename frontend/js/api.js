const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
  ? "http://localhost:5001"
  : "";

// ── Token storage ─────────────────────────────────────────────────────────────

export const token = {
  get: () => localStorage.getItem("cs_token"),
  set: (t) => localStorage.setItem("cs_token", t),
  clear: () => localStorage.removeItem("cs_token"),
};

// ── Core fetch wrapper ────────────────────────────────────────────────────────

async function request(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...options.headers };
  const t = token.get();
  if (t) headers["Authorization"] = `Bearer ${t}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    token.clear();
    window.location.href = "/admin.html";
    return;
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── Public API ────────────────────────────────────────────────────────────────

export const api = {
  // Places
  places: {
    list:   (params = {}) => request("/api/places?" + new URLSearchParams(params)),
    search: (q)           => request(`/api/places/search?q=${encodeURIComponent(q)}`),
    get:    (slug)        => request(`/api/places/${slug}`),
  },

  // Events
  events: {
    list: (params = {}) => request("/api/events?" + new URLSearchParams(params)),
  },

  // Suggestions
  suggestions: {
    submit: (data) => request("/api/suggestions", { method: "POST", body: JSON.stringify(data) }),
  },

  // Auth
  auth: {
    login:       (username, password) =>
      request("/api/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
    createAdmin: (username, password) =>
      request("/api/auth/create-admin", { method: "POST", body: JSON.stringify({ username, password }) }),
  },

  // Admin
  admin: {
    // Places
    places: {
      list:          ()         => request("/api/admin/places"),
      create:        (data)     => request("/api/admin/places", { method: "POST", body: JSON.stringify(data) }),
      update:        (id, data) => request(`/api/admin/places/${id}`, { method: "PUT", body: JSON.stringify(data) }),
      delete:        (id)       => request(`/api/admin/places/${id}`, { method: "DELETE" }),
      toggleActive:  (id)       => request(`/api/admin/places/${id}/toggle-active`, { method: "PUT" }),
      toggleVerified:(id)       => request(`/api/admin/places/${id}/toggle-verified`, { method: "PUT" }),
    },
    // Suggestions
    suggestions: {
      list:    (status = "pending") => request(`/api/admin/suggestions?status=${status}`),
      approve: (id)                 => request(`/api/admin/suggestions/${id}/approve`, { method: "PUT" }),
      reject:  (id, notes = "")    => request(`/api/admin/suggestions/${id}/reject`, { method: "PUT", body: JSON.stringify({ notes }) }),
    },
    // Events
    events: {
      list:   ()         => request("/api/admin/events"),
      create: (data)     => request("/api/admin/events", { method: "POST", body: JSON.stringify(data) }),
      update: (id, data) => request(`/api/admin/events/${id}`, { method: "PUT", body: JSON.stringify(data) }),
      delete: (id)       => request(`/api/admin/events/${id}`, { method: "DELETE" }),
    },
    // Settings
    settings: {
      get:    ()     => request("/api/admin/settings"),
      update: (data) => request("/api/admin/settings", { method: "PUT", body: JSON.stringify(data) }),
    },
    // LLM
    llm: {
      parse: (text, imageBase64, imageMediaType) =>
        request("/api/admin/llm-parse", {
          method: "POST",
          body: JSON.stringify({ text, image_base64: imageBase64, image_media_type: imageMediaType }),
        }),
    },
  },
};
