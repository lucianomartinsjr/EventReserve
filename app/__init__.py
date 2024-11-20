from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from config import Config
from flask_migrate import Migrate
import logging
import sys

# Configuração de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

db = SQLAlchemy()
socketio = SocketIO(
    logger=True,
    engineio_logger=True,
    cors_allowed_origins="*",
    ping_timeout=5,
    ping_interval=25
)
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Inicializar extensões
    db.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        logger=True,
        engineio_logger=True,
        ping_timeout=5,
        ping_interval=25,
        async_mode='threading'
    )
    migrate.init_app(app, db)

    # Configurar manipulação de erros para websocket
    @socketio.on_error_default
    def default_error_handler(e):
        app.logger.error(f'Erro no Socket.IO: {str(e)}')

    # Importar e configurar o events_manager
    from app.events.events_manager import events_manager
    events_manager.set_socketio(socketio)

    with app.app_context():
        from app.routes import bp as main_bp
        app.register_blueprint(main_bp)
        db.create_all()

    return app

app = create_app()

# Importar após criar a aplicação
from app import models, sockets