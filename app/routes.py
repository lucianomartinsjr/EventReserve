from flask import render_template, redirect, url_for, flash, request, current_app, session, jsonify, Response
import socketio
from app import db
from app.models import Event, Reservation, Settings, Users
from app.forms import ReservationForm, EventForm
from app.utils.event_utils import get_available_slots
from config import Config
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import DateTimeField
from app.utils.reservation_cleaner import clean_expired_reservations
from sqlalchemy.orm import joinedload
from sqlalchemy import func, and_
from functools import wraps
import json

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@current_app.route('/')
def index():
    # Limpa reservas expiradas antes de mostrar os eventos
    clean_expired_reservations()
    # Busca os eventos com a contagem de reservas
    events = db.session.query(
        Event,
        func.count(Reservation.id).label('reservation_count')
    ).outerjoin(
        Reservation, 
        and_(
            Event.id == Reservation.event_id,
            Reservation.status == 'confirmed'  # considera apenas reservas confirmadas
        )
    ).group_by(Event.id).all()

    # Prepara os dados para o template
    events_data = []
    for event, reservation_count in events:
        event_dict = event.__dict__
        event_dict['reservation_count'] = reservation_count
        events_data.append(event_dict)

    return render_template('index.html', events=events_data)

@current_app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = Users.query.filter_by(username=username).first()
        
        if user and user.password == password and user.isAdmin:
            session['admin_logged_in'] = True
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Acesso não autorizado ou credenciais inválidas', 'error')
    
    return render_template('admin_login.html')

@current_app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('admin_login'))

@current_app.route('/admin')
@admin_required
def admin():
    # Limpa reservas expiradas antes de mostrar os eventos
    clean_expired_reservations()
    # Carrega os eventos com suas reservas usando joinedload
    events = Event.query.options(joinedload(Event.reservations)).all()
    settings = Settings.get_settings()
    return render_template('admin.html', events=events, settings=settings)

@current_app.route('/reserve/<int:event_id>', methods=['GET', 'POST'])
def reserve(event_id):
    form = ReservationForm()
    event = Event.query.get_or_404(event_id)
    session_id = request.cookies.get('session_id')
    
    # Busca reserva temporária
    reservation = Reservation.query.filter_by(
        event_id=event_id,
        session_id=session_id,
        status='temporary'
    ).first()
    
    if not reservation:
        flash('Reserva temporária não encontrada ou expirada.', 'error')
        return redirect(url_for('index'))
    
    if datetime.utcnow() > reservation.expires_at:
        db.session.delete(reservation)
        db.session.commit()
        
        # Atualiza contagem de vagas após expiração
        available_slots = get_available_slots(event_id)
        socketio.emit('update_event_slots', {
            'event_id': event_id,
            'total_slots': event.total_slots,
            'reservation_count': event.total_slots - available_slots
        }, broadcast=True)
        
        flash('O tempo para confirmar a reserva expirou.', 'error')
        return redirect(url_for('index'))
    
    if form.validate_on_submit():
        reservation.user_name = form.user_name.data
        reservation.user_phone = form.user_phone.data
        reservation.status = 'confirmed'
        db.session.commit()
        
        # Atualiza contagem de vagas após confirmação
        available_slots = get_available_slots(event_id)
        socketio.emit('update_event_slots', {
            'event_id': event_id,
            'total_slots': event.total_slots,
            'reservation_count': event.total_slots - available_slots
        }, broadcast=True)
        
        flash('Reserva confirmada com sucesso!', 'success')
        return redirect(url_for('index'))
            
    return render_template('reservation.html', form=form, event=event)

@current_app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu com sucesso.')
    return redirect(url_for('index'))

@current_app.route('/create_event', methods=['GET', 'POST'])
def create_event():
    form = EventForm()
    if form.validate_on_submit():
        event = Event(
            name=form.name.data,
            total_slots=form.total_slots.data,
            available_slots=form.total_slots.data,
            date=form.date.data
        )
        db.session.add(event)
        db.session.commit()
        flash('Evento criado com sucesso!')
        return redirect(url_for('admin'))
    return render_template('create_event.html', form=form)

@current_app.route('/update_settings', methods=['POST'])
def update_settings():
    settings = Settings.get_settings()
    
    settings.max_users = int(request.form.get('max_users'))
    settings.choice_timeout = int(request.form.get('choice_timeout'))
    settings.queue_timeout = int(request.form.get('queue_timeout'))
    settings.max_events = int(request.form.get('max_events'))
    
    db.session.commit()
    flash('Configurações atualizadas com sucesso!')
    return redirect(url_for('admin'))

@current_app.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    form = EventForm()
    
    if request.method == 'GET':
        form.name.data = event.name
        form.date.data = event.date
        form.total_slots.data = event.total_slots
    
    if form.validate_on_submit():
        event.name = form.name.data
        event.date = form.date.data
        event.total_slots = form.total_slots.data
        db.session.commit()
        flash('Evento atualizado com sucesso!')
        return redirect(url_for('admin'))
        
    return render_template('edit_event.html', form=form, event=event)

@current_app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash('Evento excluído com sucesso!')
    return redirect(url_for('admin'))

@current_app.route('/api/events/<int:event_id>/reservations')
@admin_required
def get_event_reservations(event_id):
    try:
        # Busca o evento e suas reservas
        event = Event.query.get_or_404(event_id)
        reservations = Reservation.query.filter_by(event_id=event_id).all()
        
        # Formata os dados das reservas
        reservations_data = []
        for reservation in reservations:
            reservations_data.append({
                'user_name': reservation.user_name,
                'user_phone': reservation.user_phone,
                'created_at': reservation.created_at.isoformat(),
                'confirmed': reservation.status == 'confirmed'
            })
        
        return jsonify({
            'success': True,
            'reservations': reservations_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@current_app.route('/api/cancel_reservation', methods=['POST'])
def handle_page_close_reservation():
    try:
        data = json.loads(request.data)
        event_id = data.get('event_id')
        reservation_id = data.get('reservation_id')
        
        # Busca a reserva temporária
        reservation = Reservation.query.filter_by(
            id=reservation_id,
            event_id=event_id,
            status='temporary'
        ).first()
        
        if reservation:
            # Remove a reserva
            db.session.delete(reservation)
            db.session.commit()
            
            # Atualiza contagem de vagas
            event = Event.query.get(event_id)
            if event:
                socketio.emit('update_event_slots', {
                    'event_id': event_id,
                    'available_slots': event.total_slots - len(event.reservations),
                    'total_slots': event.total_slots,
                    'reservation_count': len(event.reservations)
                }, broadcast=True)
        
        return Response(status=200)
        
    except Exception as e:
        print(f"Erro ao cancelar reserva na página fechada: {str(e)}")
        db.session.rollback()
        return Response(status=500)