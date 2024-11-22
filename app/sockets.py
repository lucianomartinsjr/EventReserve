from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import Event, Reservation, Settings
from app.events.events_manager import events_manager
from datetime import datetime, timedelta

online_users = set()

@socketio.on('connect')
def handle_connect():
    user_id = request.sid
    if events_manager.add_user(user_id):
        emit('access_granted')
        emit('start_interaction_timer', {
            'timeout': events_manager.queue_timeout
        })
    else:
        queue_position = events_manager.get_queue_position(user_id)
        time_remaining = events_manager.get_queue_time_remaining(user_id)
        emit('in_queue', {
            'position': queue_position,
            'time_remaining': time_remaining,
            'queue_timeout': events_manager.queue_timeout
        })
    
    online_users.add(request.sid)
    
    # Emite atualização de status para todos os usuários
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue),
        'max_users': events_manager.max_users
    }, broadcast=True)
    emit('update_online_users', {'count': len(online_users)}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.sid
    events_manager.remove_user(user_id)
    online_users.discard(request.sid)
    
    # Emite atualização de status para todos os usuários
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue)
    }, broadcast=True)
    emit('update_online_users', {'count': len(online_users)}, broadcast=True)

@socketio.on('reserve_event')
def handle_reserve_event(data):
    event_id = data.get('event_id')
    user_id = request.sid
    event = Event.query.get_or_404(event_id)
    
    # Busca configurações do sistema
    settings = Settings.get_settings()
    choice_timeout = settings.choice_timeout  # Tempo em minutos
    
    # Verifica se já existe uma reserva temporária para este usuário
    existing_reservation = Reservation.query.filter_by(
        session_id=user_id,
        status='temporary'
    ).first()
    
    if existing_reservation:
        emit('error', {'message': 'Você já possui uma reserva temporária em andamento'})
        return
    
    if event.available_slots > 0:
        try:
            # Criar reserva temporária usando o timeout das configurações
            reservation = Reservation(
                event_id=event_id,
                session_id=user_id,
                status='temporary',
                expires_at=datetime.utcnow() + timedelta(minutes=choice_timeout)
            )
            db.session.add(reservation)
            event.available_slots -= 1
            db.session.commit()
            
            # Emite evento para o usuário que fez a reserva
            emit('reservation_created', {
                'reservation_id': reservation.id,
                'event_id': event_id,
                'expires_at': reservation.expires_at.isoformat(),
                'timeout': choice_timeout * 60  # Converte minutos para segundos
            })
            
            # Broadcast da atualização de vagas para todos
            emit('update_event_slots', {
                'event_id': event_id,
                'available_slots': event.available_slots
            }, broadcast=True)
        except Exception as e:
            db.session.rollback()
            emit('error', {'message': 'Erro ao criar reserva temporária'})
    else:
        emit('error', {'message': 'Não há mais vagas disponíveis para este evento'})

# Adicionar novo handler para expiração de reservas
@socketio.on('reservation_expired')
def handle_reservation_expired(data):
    reservation_id = data.get('reservation_id')
    reservation = Reservation.query.get(reservation_id)
    
    if reservation and reservation.status == 'temporary':
        event = Event.query.get(reservation.event_id)
        event.available_slots += 1
        db.session.delete(reservation)
        db.session.commit()
        
        # Broadcast da atualização de vagas
        emit('update_event_slots', {
            'event_id': event.id,
            'available_slots': event.available_slots
        }, broadcast=True)

@socketio.on('interaction_timeout')
def handle_interaction_timeout():
    user_id = request.sid
    # Move o usuário para o final da fila e obtém o próximo usuário
    next_user = events_manager.move_to_end_of_queue(user_id)
    
    # Notifica o usuário atual que foi movido para a fila
    queue_position = events_manager.get_queue_position(user_id)
    time_remaining = events_manager.get_queue_time_remaining(user_id)
    emit('moved_to_queue', {
        'position': queue_position,
        'time_remaining': time_remaining,
        'queue_timeout': events_manager.queue_timeout
    })
    
    # Se houver um próximo usuário, concede acesso a ele
    if next_user:
        emit('access_granted', room=next_user)
        emit('start_interaction_timer', {
            'timeout': events_manager.queue_timeout
        }, room=next_user)
    
    # Atualiza o status para todos os usuários
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue),
        'max_users': events_manager.max_users
    }, broadcast=True)