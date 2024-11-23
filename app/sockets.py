from flask import request
from flask_socketio import emit, join_room, leave_room
from app import socketio, db
from app.models import Event, Reservation, Settings
from app.events.events_manager import events_manager
from datetime import datetime, timedelta, UTC
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
        })

@socketio.on('connect')
def handle_connect(auth=None):
    clean_expired_reservations()
    events_manager.cleanup_disconnected_users()
    user_id = request.sid
    print(f"Usuário {user_id} conectou")
    
    if events_manager.add_user(user_id):
        print(f"Acesso concedido para usuário {user_id}")
        emit('access_granted')
        emit('start_interaction_timer', {
            'timeout': events_manager.queue_timeout
        })
    else:
        queue_position = events_manager.get_queue_position(user_id)
        time_remaining = events_manager.get_queue_time_remaining(user_id)
        print(f"Usuário {user_id} na fila: posição={queue_position}, tempo_restante={time_remaining}")
        emit('in_queue', {
            'position': queue_position,
            'time_remaining': time_remaining,
            'queue_timeout': events_manager.queue_timeout
        })
    
    online_users.add(request.sid)
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue),
        'max_users': events_manager.max_users,
        'browser_info': events_manager.user_browser_info
    })
    emit('update_online_users', {'count': len(online_users)}, broadcast=True)
    events = Event.query.all()
    for event in events:
        broadcast_event_update(event.id)

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.sid
    print(f"Usuário {user_id} desconectou")
    
    try:
        # Cancela todas as reservas temporárias do usuário
        temp_reservations = Reservation.query.filter_by(
            session_id=user_id,
            status='temporary'
        ).all()
        
        for reservation in temp_reservations:
            event_id = reservation.event_id
            db.session.delete(reservation)
            db.session.commit()
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
    
    except Exception as e:
        print(f"Erro ao limpar reservas temporárias na desconexão: {str(e)}")
        db.session.rollback()
    
    events_manager.remove_user(user_id)
    events_manager.cleanup_disconnected_users()
    online_users.discard(request.sid)
    
    # Emite atualização de status para todos os usuários
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue)
    }, broadcast=True)
    emit('update_online_users', {'count': len(online_users)}, broadcast=True)

@socketio.on('reserve_event')
def handle_reserve_event(data):
    try:
        event_id = data.get('event_id')
        user_id = request.sid
        settings = Settings.get_settings()
        
        choice_timeout = settings.choice_timeout
        if choice_timeout > 300:
            choice_timeout = 120
        
        # Criar reserva temporária
        reservation = Reservation(
            event_id=event_id,
            session_id=user_id,
            status='temporary',
            expires_at=datetime.now(UTC) + timedelta(seconds=choice_timeout)
        )
        
        db.session.add(reservation)
        db.session.commit()
        
        # Emitir evento para mostrar o modal com o timer
        emit('show_reservation_modal', {
            'event_id': event_id,
            'reservation_id': reservation.id,
            'timeout': choice_timeout
        })
        
        # Atualizar status para todos os usuários
        socketio.emit('update_users_status', {
            'active_users': list(events_manager.active_users),
            'queue': list(events_manager.waiting_queue),
            'reserving_user': user_id,
            'event_id': event_id
        })
        
        # Atualizar contagem de vagas para todos
        broadcast_event_update(event_id)
        
    except Exception as e:
        print(f"Erro ao reservar evento: {str(e)}")
        emit('error', {'message': 'Erro ao processar reserva'})

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
    })

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
            current_time = datetime.now(UTC)
            expires_at = reservation.expires_at.replace(tzinfo=UTC) if reservation.expires_at else None
            
            if expires_at and current_time > expires_at:
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
        # Busca a reserva temporária
        reservation = Reservation.query.filter_by(
            id=reservation_id,
            event_id=event_id,
            session_id=user_id,
            status='temporary'  # Garante que só cancela reservas temporárias
        ).first()
        
        if reservation:
            # Calcula o tempo restante antes de cancelar a reserva
            time_elapsed = (datetime.now(UTC) - reservation.created_at.replace(tzinfo=UTC)).total_seconds()
            remaining_interaction_time = max(0, events_manager.queue_timeout - time_elapsed)
            
            # Remove a reserva
            db.session.delete(reservation)
            db.session.commit()
            
            # Atualizar status para todos os usuários
            socketio.emit('update_users_status', {
                'active_users': list(events_manager.active_users),
                'queue': list(events_manager.waiting_queue),
                'reserving_user': None,
                'event_id': None
            })
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
            
            emit('reservation_cancelled', {
                'event_id': event_id,
                'message': 'Reserva cancelada com sucesso',
                'remaining_time': remaining_interaction_time
            })
            
        else:
            emit('error', {'message': 'Reserva não encontrada ou já expirada'})
            
    except Exception as e:
        print(f"Erro ao cancelar reserva: {str(e)}")
        db.session.rollback()
        emit('error', {'message': 'Erro ao cancelar reserva'})

# Adicionar novo handler para modal fechado
@socketio.on('modal_closed')
def handle_modal_closed(data):
    event_id = data.get('event_id')
    reservation_id = data.get('reservation_id')
    user_id = request.sid
    
    try:
        # Busca a reserva temporária
        reservation = Reservation.query.filter_by(
            id=reservation_id,
            event_id=event_id,
            session_id=user_id,
            status='temporary'
        ).first()
        
        if reservation:
            # Remove a reserva
            db.session.delete(reservation)
            db.session.commit()
            
            # Broadcast da atualização de vagas
            broadcast_event_update(event_id)
            
    except Exception as e:
        print(f"Erro ao limpar reserva após fechar modal: {str(e)}")
        db.session.rollback()

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
                expires_at=datetime.now(UTC) + timedelta(minutes=choice_timeout)
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

@socketio.on('browser_info')
def handle_browser_info(data):
    """Handler para receber e armazenar informações do navegador"""
    user_id = request.sid
    events_manager.set_user_browser_info(user_id, data)
    
    # Atualiza o status para todos os usuários com as novas informações do navegador
    emit('update_users_status', {
        'active_users': list(events_manager.active_users),
        'queue': list(events_manager.waiting_queue),
        'browser_info': events_manager.user_browser_info
    })