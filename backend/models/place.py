from extensions import db
from datetime import datetime, timezone

class Place(db.Model):
    __tablename__ = "places"

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String, nullable=False)
    slug          = db.Column(db.String, nullable=False, unique=True)
    city          = db.Column(db.String, nullable=False)
    country       = db.Column(db.String, nullable=False)
    lat           = db.Column(db.Float)
    lng           = db.Column(db.Float)
    type          = db.Column(db.String)   # chess_board | chess_shop | chess_bar | chess_club | chess_meetup | chess_memorial | chess_museum
    description   = db.Column(db.Text)
    schedule_notes = db.Column(db.Text)   # free text e.g. "Every Tuesday 7pm"
    schedule_days  = db.Column(db.String) # comma-sep e.g. "mon,wed,fri"
    website       = db.Column(db.String)
    image_url     = db.Column(db.String)
    verified      = db.Column(db.Boolean, nullable=False, default=False)
    active        = db.Column(db.Boolean, nullable=False, default=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                              onupdate=lambda: datetime.now(timezone.utc))

    events = db.relationship("Event", back_populates="place", lazy="dynamic")

    def to_dict(self):
        return {
            "id":              self.id,
            "name":            self.name,
            "slug":            self.slug,
            "city":            self.city,
            "country":         self.country,
            "lat":             self.lat,
            "lng":             self.lng,
            "type":            self.type,
            "description":     self.description,
            "schedule_notes":  self.schedule_notes,
            "schedule_days":   self.schedule_days,
            "website":         self.website,
            "image_url":       self.image_url,
            "verified":        self.verified,
            "active":          self.active,
            "created_at":      self.created_at.isoformat() if self.created_at else None,
            "updated_at":      self.updated_at.isoformat() if self.updated_at else None,
        }

    @staticmethod
    def make_slug(name, session):
        import re
        base = re.sub(r"[\s_-]+", "-", re.sub(r"[^\w\s-]", "", name.lower().strip()))
        slug, i = base, 2
        while session.query(Place).filter_by(slug=slug).first():
            slug = f"{base}-{i}"
            i += 1
        return slug
