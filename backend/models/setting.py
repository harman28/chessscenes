from extensions import db

class Setting(db.Model):
    __tablename__ = "settings"

    key   = db.Column(db.String, primary_key=True)
    value = db.Column(db.String, nullable=False)

    @staticmethod
    def get(session, key, default=None):
        row = session.get(Setting, key)
        return row.value if row else default

    @staticmethod
    def set(session, key, value):
        row = session.get(Setting, key)
        if row:
            row.value = str(value)
        else:
            session.add(Setting(key=key, value=str(value)))
