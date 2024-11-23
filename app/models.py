from datetime import datetime, UTC
from app import db

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    date = db.Column(db.DateTime, nullable=False)
    reservations = db.relationship('Reservation', backref='event', lazy='joined')

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_name = db.Column(db.String(100))
    user_phone = db.Column(db.String(20))
    status = db.Column(db.String(20), default='temporary')  # 'temporary' ou 'confirmed'
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    session_id = db.Column(db.String(100))

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_users = db.Column(db.Integer, default=3)
    choice_timeout = db.Column(db.Integer, default=30)  # tempo em segundos para escolher
    queue_timeout = db.Column(db.Integer, default=120)   # tempo em segundos na fila
    max_events = db.Column(db.Integer, default=10)        # máximo de eventos por usuário
    
    @classmethod
    def get_settings(cls):
        settings = cls.query.first()
        if not settings:
            settings = cls(
                max_users=3,
                choice_timeout=30,
                queue_timeout=120,
                max_events=5
            )
            db.session.add(settings)
            db.session.commit()
        return settings

class Users(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    isAdmin = db.Column(db.Boolean, default=False)

    @classmethod
    def init_default_admin(cls, app):
        with app.app_context():
            if not cls.query.filter_by(username=app.config['ADMIN_USERNAME']).first():
                users = cls(
                    username=app.config['ADMIN_USERNAME'],
                    password=app.config['ADMIN_PASSWORD'],
                    isAdmin=True
                )
                db.session.add(users)
                db.session.commit()