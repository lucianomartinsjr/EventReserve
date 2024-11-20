from flask import current_app, request
from flask_socketio import emit
from app import socketio, db, app
from app.models import Event, Reservation
from app.events.events_manager import events_manager
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import time
from threading import Thread

online_users = set()
scheduler = BackgroundScheduler()
connection_checker = BackgroundScheduler()

def check_active_connections():
    """Verifica periodicamente as conexões ativas e atualiza o estado"""
    current_app.logger.info("Verificando conexões ativas...")
    
    # Obter lista atual de conexões ativas
    connected_sids = set(socketio.server.manager.rooms.get('/', set()))
    
    # Atualizar conjunto de usuários online
    global online_users
    old_count = len(online_users)
    online_users = connected_sids
    
    # Forçar limpeza no events_manager
    events_manager.cleanup_disconnected_users()
    
    # Se houve mudança no número de usuários, emitir atualizações
    if old_count != len(online_users):
        socketio.emit('update_online_users', {
            'count': len(online_users)
        }, broadcast=True)
        
        socketio.emit('update_queue', {
            'queue': list(events_manager.waiting_queue)
        }, broadcast=True)
        
        socketio.emit('update_active_users', {
            'active_users': events_manager.get_active_users()
        }, broadcast=True)

def cleanup_expired_reservations():
    expired_reservations = Reservation.query.filter(
        Reservation.status == 'temporary',
        Reservation.expires_at < datetime.utcnow()
    ).all()
    
    for reservation in expired_reservations:
        event = Event.query.get(reservation.event_id)
        if event:
            event.available_slots += 1
        db.session.delete(reservation)
    
    if expired_reservations:
        db.session.commit()
        for reservation in expired_reservations:
            socketio.emit('event_updated', {
                'event_id': reservation.event_id,
                'available_slots': Event.query.get(reservation.event_id).available_slots
            }, broadcast=True)

# Iniciar os schedulers apenas quando o aplicativo estiver pronto
def init_schedulers():
    def run_with_context(func):
        def wrapper():
            with app.app_context():
                func()
        return wrapper
    
    scheduler.add_job(
        run_with_context(cleanup_expired_reservations),
        'interval',
        seconds=30
    )
    scheduler.start()
    
    connection_checker.add_job(
        run_with_context(check_active_connections),
        'interval',
        seconds=5
    )
    connection_checker.start()

# Chamar init_schedulers após a criação do app
init_schedulers()

@socketio.on('connect')
def handle_connect(auth):
    user_id = request.sid
    current_app.logger.info(f"Novo usuário conectado: {user_id}")
    online_users.add(user_id)
    
    timeout = current_app.config['DEFAULT_CHOICE_TIMEOUT']
    if events_manager.add_user(user_id, timeout):
        emit('access_granted')
        emit('start_timer', {'time': timeout})
    else:
        queue_position = list(events_manager.waiting_queue).index(user_id) + 1
        emit('in_queue', {'position': queue_position})
    
    emit('update_online_users', {'count': len(online_users)}, broadcast=True)
    emit('update_queue', {'queue': list(events_manager.waiting_queue)}, broadcast=True)
    emit('update_active_users', {'active_users': events_manager.get_active_users()}, broadcast=True)

@socketio.on('start_timer')
def handle_start_timer(data):
    user_id = request.sid
    time_left = data.get('time')
    events_manager.update_timer(user_id, time_left)
    emit('update_active_users', {'active_users': events_manager.get_active_users()}, broadcast=True)

def update_timers():
    while True:
        with app.app_context():
            active_users = events_manager.get_active_users()
            for user in active_users:
                if user['timeLeft'] > 0:
                    events_manager.update_timer(user['id'], user['timeLeft'] - 1)
                    # Corrigido: removido o parâmetro broadcast
                    socketio.emit('update_active_users', {
                        'active_users': events_manager.get_active_users()
                    }, namespace='/')  # Adicionado namespace explícito
                else:
                    socketio.emit('time_expired', room=user['id'])
                    events_manager.remove_user(user['id'])
                    # Corrigido: removido o parâmetro broadcast
                    socketio.emit('update_active_users', {
                        'active_users': events_manager.get_active_users()
                    }, namespace='/')  # Adicionado namespace explícito
        time.sleep(1)

# Iniciar thread para atualização dos timers
timer_thread = Thread(target=update_timers, daemon=True)
timer_thread.start()

@socketio.on('time_expired')
def handle_time_expired():
    user_id = request.sid
    events_manager.remove_user(user_id)
    emit('stop_timer')
    
    emit('update_queue', {'queue': list(events_manager.waiting_queue)}, broadcast=True)
    emit('update_active_users', {'active_users': events_manager.get_active_users()}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.sid
    current_app.logger.info(f"Usuário desconectado: {user_id}")
    
    # Forçar verificação imediata após desconexão
    check_active_connections()
    
    # Remover das estruturas de dados
    online_users.discard(user_id)
    events_manager.remove_user(user_id)
    
    # Forçar limpeza de usuários desconectados
    events_manager.cleanup_disconnected_users()
    
    # Emitir atualizações para todos os usuários conectados
    with current_app.app_context():
        socketio.emit('update_online_users', {
            'count': len(online_users)
        }, broadcast=True)
        
        socketio.emit('update_queue', {
            'queue': list(events_manager.waiting_queue)
        }, broadcast=True)
        
        socketio.emit('update_active_users', {
            'active_users': events_manager.get_active_users()
        }, broadcast=True)

@socketio.on_error_default
def default_error_handler(e):
    current_app.logger.error(f'Erro no Socket.IO: {str(e)}')
    # Limpar recursos do usuário em caso de erro
    handle_disconnect()

@socketio.on('reserve_event')
def handle_reserve_event(data):
    user_id = request.sid
    if user_id not in events_manager.active_users:
        emit('error', {'message': 'Usuário não tem permissão para reservar'})
        return
        
    event_id = data.get('event_id')
    event = Event.query.get_or_404(event_id)
    
    # Verificar se o usuário já tem uma reserva temporária ativa
    existing_reservation = Reservation.query.filter_by(
        event_id=event_id,
        status='temporary'
    ).first()
    
    if existing_reservation and not existing_reservation.is_expired():
        emit('error', {'message': 'Este evento já possui uma reserva temporária'})
        return
    
    if event.available_slots > 0:
        # Se existir uma reserva expirada, removê-la
        if existing_reservation:
            db.session.delete(existing_reservation)
            
        # Calcular o tempo de expiração usando a configuração
        expiration_time = datetime.utcnow() + timedelta(seconds=current_app.config['DEFAULT_CONFIRMATION_TIMEOUT'])
        reservation = Reservation(
            event_id=event_id,
            status='temporary',
            expires_at=expiration_time
        )
        db.session.add(reservation)
        event.available_slots -= 1
        db.session.commit()
        
        # Notificar todos os usuários
        emit('event_updated', {
            'event_id': event_id,
            'available_slots': event.available_slots
        }, broadcast=True)
        
        # Enviar dados da reserva para o usuário
        emit('reservation_created', {
            'reservation_id': reservation.id,
            'event_id': event_id,
            'expires_at': reservation.expires_at.isoformat(),
            'confirmation_timeout': current_app.config['DEFAULT_CONFIRMATION_TIMEOUT']
        })

@socketio.on('confirm_reservation')
def handle_confirm_reservation(data):
    reservation_id = data.get('reservation_id')
    name = data.get('name')
    phone = data.get('phone')
    
    reservation = Reservation.query.get(reservation_id)
    if not reservation or reservation.status != 'temporary':
        emit('error', {'message': 'Reserva não encontrada ou já expirada'})
        return
        
    if reservation.expires_at < datetime.utcnow():
        db.session.delete(reservation)
        db.session.commit()
        emit('error', {'message': 'Reserva expirada'})
        return
        
    # Confirmar a reserva
    reservation.status = 'confirmed'
    reservation.user_name = name
    reservation.user_phone = phone
    db.session.commit()
    
    emit('reservation_confirmed', {'success': True})