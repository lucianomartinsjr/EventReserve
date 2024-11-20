from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange

class ReservationForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(min=3, max=100)])
    phone = StringField('Telefone', validators=[DataRequired(), Length(min=10, max=20)])
    submit = SubmitField('Confirmar Reserva')

class EventForm(FlaskForm):
    name = StringField('Nome do Evento', validators=[DataRequired(), Length(min=3, max=100)])
    total_slots = IntegerField('Número de Vagas', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Criar Evento')