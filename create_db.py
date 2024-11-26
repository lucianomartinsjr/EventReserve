import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_users = db.Column(db.Integer, default=1)
    choice_timeout = db.Column(db.Integer, default=120)
    queue_timeout = db.Column(db.Integer, default=300)
    max_events = db.Column(db.Integer, default=100)

with app.app_context():
    db.create_all()
    
    if not Settings.query.first():

        settings = Settings(
            max_users=Config.MAX_USERS,
            queue_timeout=Config.QUEUE_TIMEOUT,
            choice_timeout=Config.CHOICE_TIMEOUT,
            max_events=Config.MAX_EVENTS
        )
        db.session.add(settings)
        db.session.commit()
        
    print("Banco de dados criado com sucesso!") 