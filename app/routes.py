from flask import render_template, redirect, url_for, flash, request, current_app, session
from app import db
from app.models import Event, Reservation
from app.forms import ReservationForm, EventForm
from config import Config

@current_app.route('/')
def index():
    events = Event.query.all()
    return render_template('index.html', events=events, max_users=Config.DEFAULT_MAX_USERS)

@current_app.route('/admin')
def admin():
    events = Event.query.all()
    form = EventForm()
    return render_template('admin.html', events=events, form=form)

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