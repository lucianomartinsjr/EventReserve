from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import Event, Reservation, Settings
from app.events.events_manager import events_manager
from datetime import datetime, timedelta
from app.utils.reservation_cleaner import clean_expired_reservations
from sqlalchemy.sql import func
from sqlalchemy import and_, or_
from app.utils.event_utils import get_available_slots

online_users = set()

def broadcast_event_update(event_id):
    """Função auxiliar para emitir atualização de vagas para todos os usuários"""
    event = Event.query.get(event_id)
    if event:
        vacancies = event.total_slots - len(event.reservations)
        print(f"Atualizando evento {event.id}: total={event.total_slots}, reservadas={len(event.reservations)}, vagas={vacancies}")
        socketio.emit('update_event_slots', {
            'event_id': event.id,
            'available_slots': vacancies,
            'total_slots': event.total_slots,
            'reservation_count': len(event.reservations)
        }, to=None)

@socketio.on('connect')
def handle_connect(auth=None):
    # Limpa reservas expiradas quando um usuário se conecta
    clean_expired_reservations()
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
    }, to=None)
    emit('update_online_users', {'count': len(online_users)}, to=None)
    
    # Adiciona atualização inicial das vagas para todos os eventos
    events = Event.query.all()
    for event in events:
        broadcast_event_update(event.id)

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.sid
    events_manager.remove_user(user_id)
    online_users.discard(request.sid)
    
    # Emite atualização de status para todos os usuários
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue)
    }, to=None)
    emit('update_online_users', {'count': len(online_users)}, to=None)

@socketio.on('reserve_event')
def handle_reserve_event(data):
    try:
        clean_expired_reservations()
        event_id = data.get('event_id')
        user_id = request.sid
        
        # Verifica se o evento existe
        event = Event.query.get(event_id)
        if not event:
            emit('error', {'message': 'Evento não encontrado'})
            return
        
        # Calcula vagas disponíveis
        available_slots = get_available_slots(event_id)
        print(f"Vagas disponíveis para evento {event_id}: {available_slots}") # Debug
        
        # Verifica se há vagas disponíveis
        if available_slots <= 0:
            emit('error', {'message': 'Não há mais vagas disponíveis para este evento'})
            return
            
        settings = Settings.get_settings()
        choice_timeout = settings.choice_timeout
        
        # Verifica se já existe uma reserva temporária para este usuário
        existing_reservation = Reservation.query.filter_by(
            event_id=event_id,
            session_id=user_id,
            status='temporary'
        ).first()
        
        if existing_reservation:
            emit('error', {'message': 'Você já possui uma reserva temporária para este evento'})
            return
        
        # Verifica novamente se ainda há vagas antes de criar a reserva
        if get_available_slots(event_id) <= 0:
            emit('error', {'message': 'Desculpe, as vagas acabaram de ser preenchidas'})
            return
            
        # Cria reserva temporária
        reservation = Reservation(
            event_id=event_id,
            session_id=user_id,
            status='temporary',
            expires_at=datetime.utcnow() + timedelta(minutes=choice_timeout)
        )
        
        db.session.add(reservation)
        db.session.commit()
        
        print(f"Reserva temporária criada: {reservation.id}") # Debug
        
        # Emite atualização imediata para todos
        broadcast_event_update(event_id)
        
        # Mostra o modal de reserva
        emit('show_reservation_modal', {
            'event_id': event_id,
            'reservation_id': reservation.id,
            'timeout': choice_timeout * 60
        })
            
    except Exception as e:
        print(f"Erro ao processar reserva: {str(e)}") # Debug
        db.session.rollback()
        emit('error', {'message': 'Erro ao iniciar processo de reserva'})

# Adicionar novo handler para expiração de reservas
@socketio.on('reservation_expired')
def handle_reservation_expired(data):
    reservation_id = data.get('reservation_id')
    reservation = Reservation.query.get(reservation_id)
    
    if reservation and reservation.status == 'temporary':
        event_id = reservation.event_id
        db.session.delete(reservation)
        db.session.commit()
        
        # Broadcast da atualização de vagas
        broadcast_event_update(event_id)

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
    }, to=None)

@socketio.on('confirm_reservation')
def handle_confirm_reservation(data):
    event_id = data.get('event_id')
    user_id = request.sid
    user_name = data.get('user_name')
    user_phone = data.get('user_phone')
    
    reservation = Reservation.query.filter_by(
        event_id=event_id,
        session_id=user_id,
        status='temporary'
    ).first()
    
    if reservation:
        try:
            if datetime.utcnow() > reservation.expires_at:
                db.session.delete(reservation)
                db.session.commit()
                emit('error', {'message': 'O tempo para confirmar a reserva expirou'})
                return
            
            reservation.status = 'confirmed'
            reservation.user_name = user_name
            reservation.user_phone = user_phone
            reservation.expires_at = None
            db.session.commit()
            
            event = Event.query.get(event_id)
            event_name = event.name if event else "evento"
            
            # Recalcula vagas disponíveis
            available_slots = get_available_slots(event_id)
            
            emit('reservation_success', {
                'event_id': event_id,
                'message': f'Sua reserva para {event_name} foi confirmada com sucesso!'
            })
            
            emit('close_reservation_modal')
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
            
        except Exception as e:
            db.session.rollback()
            emit('error', {'message': 'Erro ao confirmar reserva'})
    else:
        emit('error', {'message': 'Reserva temporária não encontrada'})

@socketio.on('cancel_reservation')
def handle_cancel_reservation(data):
    event_id = data.get('event_id')
    reservation_id = data.get('reservation_id')
    user_id = request.sid
    
    try:
        print(f"Cancelando reserva: event_id={event_id}, reservation_id={reservation_id}") # Debug
        
        # Busca a reserva com lock para evitar condições de corrida
        reservation = Reservation.query.filter_by(
            id=reservation_id,
            event_id=event_id,
            session_id=user_id
        ).with_for_update().first()
        
        if reservation:
            db.session.delete(reservation)
            db.session.commit()
            
            print(f"Reserva {reservation_id} cancelada com sucesso") # Debug
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
            
            emit('reservation_cancelled', {
                'event_id': event_id,
                'message': 'Reserva cancelada com sucesso'
            })
            
            # Emite evento para reabilitar o botão
            emit('enable_reserve_button', {
                'event_id': event_id
            })
        else:
            print(f"Reserva não encontrada: event_id={event_id}, reservation_id={reservation_id}") # Debug
            emit('error', {'message': 'Reserva não encontrada ou já expirada'})
            
    except Exception as e:
        print(f"Erro ao cancelar reserva: {str(e)}") # Debug
        db.session.rollback()
        emit('error', {'message': 'Erro ao cancelar reserva'})

@socketio.on('create_temporary_reservation')
def handle_create_temporary_reservation(data):
    event_id = data.get('event_id')
    user_id = request.sid
    user_name = data.get('user_name')
    user_phone = data.get('user_phone')
    
    event = Event.query.get_or_404(event_id)
    settings = Settings.get_settings()
    choice_timeout = settings.choice_timeout
    
    if event.available_slots > 0:
        try:
            # Criar reserva temporária
            reservation = Reservation(
                event_id=event_id,
                session_id=user_id,
                user_name=user_name,
                user_phone=user_phone,
                status='temporary',
                expires_at=datetime.utcnow() + timedelta(minutes=choice_timeout)
            )
            db.session.add(reservation)
            event.available_slots -= 1
            db.session.commit()
            
            emit('temporary_reservation_created', {
                'event_id': event_id,
                'reservation_id': reservation.id
            })
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
            
        except Exception as e:
            db.session.rollback()
            emit('error', {'message': 'Erro ao criar reserva temporária'})
    else:
        emit('error', {'message': 'Não há mais vagas disponíveis para este evento'})