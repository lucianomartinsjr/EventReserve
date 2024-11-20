from flask_wtf import FlaskForm
from wtforms import StringField, DateTimeField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Length

class ReservationForm(FlaskForm):
    name = StringField('Nome', validators=[
        DataRequired(message='Nome é obrigatório'),
        Length(min=3, max=100, message='O nome deve ter entre 3 e 100 caracteres')
    ])
    phone = StringField('Telefone', validators=[
        DataRequired(message='Telefone é obrigatório'),
        Length(min=10, max=20, message='Telefone inválido')
    ])
    submit = SubmitField('Confirmar Reserva')

class EventForm(FlaskForm):
    name = StringField('Nome do Evento', 
        validators=[
            DataRequired(message='Nome é obrigatório'),
            Length(min=3, max=100, message='O nome deve ter entre 3 e 100 caracteres')
        ])
    
    date = DateTimeField('Data do Evento',
        validators=[DataRequired(message='Data é obrigatória')],
        format='%Y-%m-%dT%H:%M',
        render_kw={"type": "datetime-local"})
    
    total_slots = IntegerField('Total de Vagas',
        validators=[
            DataRequired(message='Número de vagas é obrigatório'),
            NumberRange(min=1, message='O número de vagas deve ser maior que zero')
        ])
    
    submit = SubmitField('Criar Evento')