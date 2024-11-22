from datetime import datetime, UTC
from app import db

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    date = db.Column(db.DateTime, nullable=False)
    reservations = db.relationship('Reservation', backref='event', lazy=True)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_name = db.Column(db.String(100))
    user_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='temporary')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    expires_at = db.Column(db.DateTime)
    session_id = db.Column(db.String(100))

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_users = db.Column(db.Integer, default=3)
    choice_timeout = db.Column(db.Integer, default=120)  # tempo em segundos para escolher
    queue_timeout = db.Column(db.Integer, default=300)   # tempo em segundos na fila
    max_events = db.Column(db.Integer, default=5)        # máximo de eventos por usuário
    
    @classmethod
    def get_settings(cls):
        settings = cls.query.first()
        if not settings:
            settings = cls(
                max_users=3,
                choice_timeout=120,
                queue_timeout=300,
                max_events=5
            )
            db.session.add(settings)
            db.session.commit()
        return settings