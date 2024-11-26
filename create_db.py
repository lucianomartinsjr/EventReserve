import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

# Criar uma nova instância do Flask apenas para criar o banco
app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# Importar o modelo Settings depois de criar db
class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    max_users = db.Column(db.Integer, default=1)
    choice_timeout = db.Column(db.Integer, default=120)
    queue_timeout = db.Column(db.Integer, default=300)
    max_events = db.Column(db.Integer, default=100)

with app.app_context():
    # Cria todas as tabelas
    db.create_all()
    
    # Verifica se já existem configurações
    if not Settings.query.first():
        # Cria configurações iniciais
        settings = Settings(
            max_users=Config.MAX_USERS,
            queue_timeout=Config.QUEUE_TIMEOUT,
            choice_timeout=Config.CHOICE_TIMEOUT,
            max_events=Config.MAX_EVENTS
        )
        db.session.add(settings)
        db.session.commit()
        
    print("Banco de dados criado com sucesso!") 