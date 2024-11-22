from flask import render_template, redirect, url_for, flash, request, current_app, session
from app import db
from app.models import Event, Reservation, Settings
from app.forms import ReservationForm, EventForm
from config import Config
from datetime import datetime
from flask_wtf import FlaskForm
from wtforms import DateTimeField

@current_app.route('/')
def index():
    events = Event.query.all()
    return render_template('index.html', events=events, max_users=Config.DEFAULT_MAX_USERS)

@current_app.route('/admin')
def admin():
    events = Event.query.all()
    settings = Settings.get_settings()
    return render_template('admin.html', events=events, settings=settings)

@current_app.route('/reserve/<int:event_id>', methods=['GET', 'POST'])
def reserve(event_id):
    form = ReservationForm()
    event = Event.query.get_or_404(event_id)
    
    if form.validate_on_submit():
        reservation = Reservation.query.filter_by(
            event_id=event_id,
            status='temporary'
        ).first()
        
        if reservation:
            reservation.user_name = form.name.data
            reservation.user_phone = form.phone.data
            reservation.status = 'confirmed'
            db.session.commit()
            flash('Reserva confirmada com sucesso!')
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
        event = Event(name=form.name.data, date=form.date.data, total_slots=form.total_slots.data)
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