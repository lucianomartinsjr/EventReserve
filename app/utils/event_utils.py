from app.models import Event, Reservation

def get_available_slots(event_id):
    """
    Calcula o número de vagas disponíveis para um evento
    """
    event = Event.query.get(event_id)
    if not event:
        return 0
        
    # Conta todas as reservas (temporárias e confirmadas)
    total_reservations = Reservation.query.filter(
        Reservation.event_id == event_id,
        Reservation.status.in_(['temporary', 'confirmed'])
    ).count()
    
    # Garante que nunca retorne um número negativo
    available_slots = max(0, event.total_slots - total_reservations)
    return available_slots 