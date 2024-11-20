from flask import render_template, redirect, url_for, flash, request, session
from app import db
from app.forms import ReservationForm, EventForm
from app.models import Event, Reservation, Settings
from datetime import datetime
from flask import Blueprint

# Criar um Blueprint para as rotas
bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    events = Event.query.all()
    settings = Settings.get_settings()
    return render_template('index.html', events=events, settings=settings)

@bp.route('/admin')
def admin():
    events = Event.query.all()
    form = EventForm()
    settings = Settings.get_settings()
    return render_template('admin.html', events=events, form=form, settings=settings)

@bp.route('/reserve/<int:event_id>', methods=['GET', 'POST'])
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
            return redirect(url_for('main.index'))
            
    return render_template('reservation.html', form=form, event=event)

@bp.route('/logout')
def logout():
    session.clear()
    flash('Você saiu com sucesso.')
    return redirect(url_for('main.index'))

@bp.route('/create_event', methods=['GET', 'POST'])
def create_event():
    try:
        form = EventForm()
        
        if form.validate_on_submit():
            event = Event(
                name=form.name.data,
                date=form.date.data,
                total_slots=form.total_slots.data,
                available_slots=form.total_slots.data
            )
            
            db.session.add(event)
            db.session.commit()
            
            flash('Evento criado com sucesso!', 'success')
            return redirect(url_for('main.admin'))
            
        return render_template('create_event.html', form=form)
        
    except Exception as e:
        print(f"Erro ao criar evento: {str(e)}")
        flash('Erro ao criar evento. Por favor, tente novamente.', 'error')
        return render_template('create_event.html', form=form)

@bp.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    try:
        event = Event.query.get_or_404(event_id)
        db.session.delete(event)
        db.session.commit()
        flash('Evento excluído com sucesso!', 'success')
    except Exception as e:
        print(f"Erro ao excluir evento: {str(e)}")
        flash('Erro ao excluir evento.', 'error')
    return redirect(url_for('main.admin'))

@bp.route('/edit_event/<int:event_id>', methods=['GET', 'POST'])
def edit_event(event_id):
    event = Event.query.get_or_404(event_id)
    form = EventForm(obj=event)
    
    if form.validate_on_submit():
        event.name = form.name.data
        event.date = form.date.data
        event.total_slots = form.total_slots.data
        event.available_slots = form.total_slots.data
        
        try:
            db.session.commit()
            flash('Evento atualizado com sucesso!', 'success')
            return redirect(url_for('main.admin'))
        except Exception as e:
            print(f"Erro ao atualizar evento: {str(e)}")
            flash('Erro ao atualizar evento.', 'error')
            
    return render_template('edit_event.html', form=form, event=event)

@bp.route('/admin/settings', methods=['POST'])
def update_settings():
    settings = Settings.get_settings()
    
    try:
        settings.update(
            max_users=int(request.form.get('max_users')),
            choice_timeout=int(request.form.get('choice_timeout')),
            queue_timeout=int(request.form.get('queue_timeout')),
            max_events=int(request.form.get('max_events'))
        )
        flash('Configurações atualizadas com sucesso!', 'success')
    except ValueError:
        flash('Erro ao atualizar configurações. Verifique os valores informados.', 'error')
    
    return redirect(url_for('main.admin'))