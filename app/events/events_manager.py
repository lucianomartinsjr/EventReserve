from threading import Lock
from collections import deque

from flask import current_app

class EventsManager:
    def __init__(self, max_users=3):
        self.max_users = max_users
        self.active_users = {}
        self.waiting_queue = deque()
        self.lock = Lock()
        self.socketio = None  #
        
    def set_socketio(self, socketio):
        self.socketio = socketio
        
    def add_user(self, user_id, timeout):
        with self.lock:
            if user_id in self.active_users or user_id in self.waiting_queue:
                return False
            if len(self.active_users) < self.max_users:
                self.active_users[user_id] = timeout
                return True
            self.waiting_queue.append(user_id)
            return False
            
    def remove_user(self, user_id):
        with self.lock:
            was_active = user_id in self.active_users
            was_in_queue = user_id in self.waiting_queue
            
            # Remover da lista de ativos
            if was_active:
                del self.active_users[user_id]
            
            # Remover da fila de espera
            try:
                self.waiting_queue.remove(user_id)
            except ValueError:
                pass
            
            # Se o usuário estava ativo, processar a fila
            if was_active:
                self._process_queue()
                
            return was_active or was_in_queue
            
    def update_timer(self, user_id, time_left):
        with self.lock:
            if user_id in self.active_users:
                self.active_users[user_id] = time_left
                
    def get_active_users(self):
        return [{"id": user_id, "timeLeft": time_left} 
                for user_id, time_left in self.active_users.items()]
                
    def _process_queue(self):
        with self.lock:
            if not self.socketio:
                return None
                
            if self.waiting_queue and len(self.active_users) < self.max_users:
                next_user = self.waiting_queue.popleft()
                self.active_users[next_user] = current_app.config['DEFAULT_CHOICE_TIMEOUT']
                # Emitir evento de acesso concedido para o próximo usuário
                self.socketio.emit('access_granted', room=next_user)
                self.socketio.emit('start_timer', {'time': current_app.config['DEFAULT_CHOICE_TIMEOUT']}, room=next_user)
                # Atualizar a fila para todos
                self.socketio.emit('update_queue', {'queue': list(self.waiting_queue)}, broadcast=True)
                # Atualizar lista de usuários ativos para todos
                self.socketio.emit('update_active_users', {
                    'active_users': self.get_active_users()
                }, broadcast=True)
                return next_user
        return None

    def cleanup_disconnected_users(self):
        with self.lock:
            changes_made = False
            
            # Verificar usuários ativos
            active_disconnected = [
                user_id for user_id in list(self.active_users.keys())  # Criar cópia para evitar modificação durante iteração
                if not self.socketio.server.manager.is_connected(user_id)
            ]
            
            # Verificar fila de espera
            queue_disconnected = [
                user_id for user_id in list(self.waiting_queue)  # Criar cópia para evitar modificação durante iteração
                if not self.socketio.server.manager.is_connected(user_id)
            ]
            
            # Remover usuários desconectados dos ativos
            for user_id in active_disconnected:
                if user_id in self.active_users:
                    del self.active_users[user_id]
                    changes_made = True
            
            # Remover usuários desconectados da fila
            if queue_disconnected:
                self.waiting_queue = deque([
                    user_id for user_id in self.waiting_queue 
                    if user_id not in queue_disconnected
                ])
                changes_made = True
            
            # Se houve alterações, processar fila e notificar
            if changes_made and self.socketio:
                self._process_queue()
                self.socketio.emit('update_queue', {
                    'queue': list(self.waiting_queue)
                }, broadcast=True)
                self.socketio.emit('update_active_users', {
                    'active_users': self.get_active_users()
                }, broadcast=True)

events_manager = EventsManager() 