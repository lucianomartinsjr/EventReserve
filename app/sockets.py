from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import Event, Reservation
from app.events.events_manager import events_manager
from datetime import datetime, timedelta

online_users = set()

@socketio.on('connect')
def handle_connect():
    user_id = request.sid
    if events_manager.add_user(user_id):
        emit('access_granted')
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
    event = Event.query.get_or_404(event_id)
    
    if event.available_slots > 0:
        # Criar reserva temporária
        reservation = Reservation(
            event_id=event_id,
            expires_at=datetime.utcnow() + timedelta(seconds=events_manager.choice_timeout)
        )
        db.session.add(reservation)
        event.available_slots -= 1
        db.session.commit()
        
        emit('reservation_created', {
            'reservation_id': reservation.id,
            'expires_at': reservation.expires_at.isoformat(),
            'timeout': events_manager.choice_timeout
        })
        
        # Broadcast para todos os usuários
        emit('update_events', {
            'event_id': event_id,
            'available_slots': event.available_slots
        }, broadcast=True)