from datetime import datetime
from app import db
from flask import current_app

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    total_slots = db.Column(db.Integer, nullable=False)
    available_slots = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    date = db.Column(db.DateTime, nullable=False)
    reservations = db.relationship('Reservation', backref='event', lazy=True)

    def __repr__(self):
        return f'<Event {self.name}>'

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    user_name = db.Column(db.String(100), nullable=False)
    user_phone = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='temporary')  # temporary, confirmed, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_users = db.Column(db.Integer, nullable=False)
    choice_timeout = db.Column(db.Integer, nullable=False)  # em segundos
    queue_timeout = db.Column(db.Integer, nullable=False)   # em segundos
    max_events = db.Column(db.Integer, nullable=False)

    @classmethod
    def get_settings(cls):
        """Retorna as configurações atuais ou cria com valores padrão do config.py"""
        settings = cls.query.first()
        if not settings:
            settings = cls(
                max_users=current_app.config['DEFAULT_MAX_USERS'],
                choice_timeout=current_app.config['DEFAULT_CHOICE_TIMEOUT'],
                queue_timeout=current_app.config['DEFAULT_QUEUE_TIMEOUT'],
                max_events=current_app.config['DEFAULT_MAX_EVENTS']
            )
            db.session.add(settings)
            db.session.commit()
        return settings

    def update(self, max_users=None, choice_timeout=None, queue_timeout=None, max_events=None):
        """Atualiza as configurações"""
        if max_users is not None:
            self.max_users = max_users
        if choice_timeout is not None:
            self.choice_timeout = choice_timeout
        if queue_timeout is not None:
            self.queue_timeout = queue_timeout
        if max_events is not None:
            self.max_events = max_events
        db.session.commit()