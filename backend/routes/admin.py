import json
import os
import urllib.request
import urllib.error

from flask import Blueprint, jsonify, request
from extensions import db
from models import Place, Event, Suggestion, Setting
from auth import require_auth

bp = Blueprint("admin", __name__)


# ── Places ────────────────────────────────────────────────────────────────────

@bp.get("/api/admin/places")
@require_auth
def list_all_places():
    places = Place.query.order_by(Place.created_at.desc()).all()
    return jsonify([p.to_dict() for p in places])


@bp.post("/api/admin/places")
@require_auth
def create_place():
    data = request.get_json() or {}
    if not data.get("name"):
        return jsonify({"error": "name is required"}), 400
    slug = Place.make_slug(data["name"], db.session)
    place = Place(
        name=data["name"], slug=slug,
        city=data.get("city", ""), country=data.get("country", ""),
        lat=data.get("lat"), lng=data.get("lng"),
        type=data.get("type"), description=data.get("description"),
        schedule_notes=data.get("schedule_notes"),
        schedule_days=data.get("schedule_days"),
        website=data.get("website"), image_url=data.get("image_url"),
        verified=data.get("verified", True),
        active=data.get("active", True),
    )
    db.session.add(place)
    db.session.commit()
    return jsonify({"message": "Place created", "slug": slug, "id": place.id}), 201


@bp.put("/api/admin/places/<int:place_id>")
@require_auth
def update_place(place_id):
    place = db.get_or_404(Place, place_id)
    data = request.get_json() or {}
    fields = ["name", "city", "country", "lat", "lng", "type", "description",
              "schedule_notes", "schedule_days", "website", "image_url",
              "verified", "active"]
    for f in fields:
        if f in data:
            setattr(place, f, data[f])
    db.session.commit()
    return jsonify(place.to_dict())


@bp.delete("/api/admin/places/<int:place_id>")
@require_auth
def delete_place(place_id):
    place = db.get_or_404(Place, place_id)
    db.session.delete(place)
    db.session.commit()
    return jsonify({"message": "Deleted"})


@bp.put("/api/admin/places/<int:place_id>/toggle-active")
@require_auth
def toggle_active(place_id):
    place = db.get_or_404(Place, place_id)
    place.active = not place.active
    db.session.commit()
    return jsonify({"id": place.id, "active": place.active})


@bp.put("/api/admin/places/<int:place_id>/toggle-verified")
@require_auth
def toggle_verified(place_id):
    place = db.get_or_404(Place, place_id)
    place.verified = not place.verified
    db.session.commit()
    return jsonify({"id": place.id, "verified": place.verified})


# ── Suggestions ───────────────────────────────────────────────────────────────

@bp.get("/api/admin/suggestions")
@require_auth
def list_suggestions():
    status = request.args.get("status", "pending")
    suggestions = (Suggestion.query
                   .filter_by(status=status)
                   .order_by(Suggestion.submitted_at.desc())
                   .all())
    return jsonify([s.to_dict() for s in suggestions])


@bp.put("/api/admin/suggestions/<int:suggestion_id>/approve")
@require_auth
def approve_suggestion(suggestion_id):
    s = db.get_or_404(Suggestion, suggestion_id)
    slug = Place.make_slug(s.name, db.session)
    place = Place(
        name=s.name, slug=slug,
        city=s.city, country=s.country,
        lat=s.lat, lng=s.lng,
        type=s.type, description=s.description,
        schedule_notes=s.schedule_notes,
        website=s.website,
        verified=False,  # approved suggestions start as unverified
        active=True,
    )
    db.session.add(place)
    s.status = "approved"
    db.session.commit()
    return jsonify({"message": "Approved — added as unverified place", "slug": slug})


@bp.put("/api/admin/suggestions/<int:suggestion_id>/reject")
@require_auth
def reject_suggestion(suggestion_id):
    s = db.get_or_404(Suggestion, suggestion_id)
    data = request.get_json() or {}
    s.status = "rejected"
    s.admin_notes = data.get("notes")
    db.session.commit()
    return jsonify({"message": "Rejected"})


# ── Events ────────────────────────────────────────────────────────────────────

@bp.get("/api/admin/events")
@require_auth
def list_all_events():
    events = Event.query.order_by(Event.event_date.desc()).all()
    return jsonify([e.to_dict() for e in events])


@bp.post("/api/admin/events")
@require_auth
def create_event():
    data = request.get_json() or {}
    for f in ["name", "city", "country", "event_date"]:
        if not data.get(f):
            return jsonify({"error": f"{f} is required"}), 400
    event = Event(
        place_id=data.get("place_id"),
        name=data["name"],
        city=data["city"],
        country=data["country"],
        lat=data.get("lat"), lng=data.get("lng"),
        event_date=data["event_date"],
        event_time=data.get("event_time"),
        description=data.get("description"),
        url=data.get("url"),
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({"message": "Event created", "id": event.id}), 201


@bp.put("/api/admin/events/<int:event_id>")
@require_auth
def update_event(event_id):
    event = db.get_or_404(Event, event_id)
    data = request.get_json() or {}
    for f in ["name", "city", "country", "lat", "lng", "event_date",
              "event_time", "description", "url", "place_id"]:
        if f in data:
            setattr(event, f, data[f])
    db.session.commit()
    return jsonify(event.to_dict())


@bp.delete("/api/admin/events/<int:event_id>")
@require_auth
def delete_event(event_id):
    event = db.get_or_404(Event, event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify({"message": "Deleted"})


# ── LLM Parse ─────────────────────────────────────────────────────────────────

LLM_PROMPT = """Extract chess venue or event details from the content below and return ONLY a JSON object with these fields:
{
  "name": "",
  "city": "",
  "country": "",
  "lat": null,
  "lng": null,
  "type": "",         // one of: chess_club, chess_bar, chess_meetup, chess_board, chess_shop, chess_memorial, chess_museum
  "description": "",
  "schedule_notes": "",
  "schedule_days": "", // comma-separated short days: mon,tue,wed,thu,fri,sat,sun
  "website": ""
}

For lat/lng: derive approximate coordinates from the city/address if possible. Return null if genuinely unknown.
Return ONLY the JSON object, no markdown, no explanation.

Content:
"""

@bp.post("/api/admin/llm-parse")
@require_auth
def llm_parse():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not configured on server"}), 500

    data = request.get_json() or {}
    text = data.get("text", "")
    image_base64 = data.get("image_base64")
    image_media_type = data.get("image_media_type")

    message_content = []
    if image_base64 and image_media_type:
        message_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": image_media_type, "data": image_base64},
        })
    message_content.append({"type": "text", "text": LLM_PROMPT + text})

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "messages": [{"role": "user", "content": message_content}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Anthropic API error {e.code}: {body}")
        return jsonify({"error": f"Anthropic API error {e.code}", "detail": body}), 502

    raw = next((b["text"] for b in result.get("content", []) if b["type"] == "text"), "")
    parsed = json.loads(raw.replace("```json", "").replace("```", "").strip())
    return jsonify(parsed)


# ── Settings ──────────────────────────────────────────────────────────────────

@bp.get("/api/admin/settings")
@require_auth
def get_settings():
    rows = Setting.query.all()
    return jsonify({r.key: r.value for r in rows})


@bp.put("/api/admin/settings")
@require_auth
def update_settings():
    data = request.get_json() or {}
    for key, value in data.items():
        Setting.set(db.session, key, value)
    db.session.commit()
    return jsonify({"message": "Settings updated"})
