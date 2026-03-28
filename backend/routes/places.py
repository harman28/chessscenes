from flask import Blueprint, jsonify, request
from extensions import db
from models import Place, Setting

bp = Blueprint("places", __name__)


def show_unverified():
    return Setting.get(db.session, "show_unverified", "true") == "true"


@bp.get("/api/places")
def list_places():
    q = Place.query.filter_by(active=True)
    if not show_unverified():
        q = q.filter_by(verified=True)

    city  = request.args.get("city",  "").strip().lower()
    type_ = request.args.get("type",  "").strip()
    day   = request.args.get("day",   "").strip().lower()  # e.g. "tue"

    if city:
        q = q.filter(db.func.lower(Place.city) == city)
    if type_:
        q = q.filter_by(type=type_)
    if day:
        q = q.filter(db.or_(
            Place.schedule_days == None,
            Place.schedule_days == "",
            Place.schedule_days.ilike(f"%{day}%"),
        ))

    places = q.order_by(Place.name).all()
    return jsonify([p.to_dict() for p in places])


@bp.get("/api/places/search")
def search_places():
    term = request.args.get("q", "").strip()
    if not term:
        return jsonify([])

    like = f"%{term.lower()}%"
    q = Place.query.filter(
        Place.active == True,
        db.or_(
            db.func.lower(Place.name).like(like),
            db.func.lower(Place.city).like(like),
            db.func.lower(Place.country).like(like),
        )
    )
    if not show_unverified():
        q = q.filter_by(verified=True)

    return jsonify([p.to_dict() for p in q.limit(20).all()])


@bp.get("/api/places/<slug>")
def get_place(slug):
    place = Place.query.filter_by(slug=slug, active=True).first_or_404()
    return jsonify(place.to_dict())
