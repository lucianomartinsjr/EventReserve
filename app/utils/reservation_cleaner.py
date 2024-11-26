from datetime import datetime
from app import db, socketio
from app.models import Reservation, Event
from app.utils.event_utils import get_available_slots

def clean_expired_reservations():
    """
    Limpa todas as reservas temporárias expiradas e atualiza as vagas dos eventos
    """
    try:
        # Busca todas as reservas temporárias expiradas
        expired_reservations = Reservation.query.filter(
            Reservation.status == 'temporary',
            Reservation.expires_at < datetime.utcnow()
        ).with_for_update().all()
        
        affected_events = set()
        
        # Para cada reserva expirada
        for reservation in expired_reservations:
            affected_events.add(reservation.event_id)
            db.session.delete(reservation)
        
        db.session.commit()
        
        # Emite atualização para cada evento afetado
        for event_id in affected_events:
            event = Event.query.get(event_id)
            if event:
                available_slots = get_available_slots(event_id)
                socketio.emit('update_event_slots', {
                    'event_id': event_id,
                    'total_slots': event.total_slots,
                    'reservation_count': event.total_slots - available_slots
                }, broadcast=True)
                
    except Exception as e:
        db.session.rollback()
        print(f"Erro ao limpar reservas expiradas: {str(e)}")