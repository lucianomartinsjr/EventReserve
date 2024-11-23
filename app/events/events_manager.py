from threading import Lock
from collections import deque
from datetime import UTC, datetime, timedelta
from app import db, socketio
from app.models import Settings

class EventsManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventsManager, cls).__new__(cls)
            cls._instance.initialize()
        return cls._instance
    
    def initialize(self):
        self.active_users = set()
        self.waiting_queue = deque()
        self.user_queue_times = {}
        self.user_browser_info = {}
        self.lock = Lock()
        self._update_settings()
        
    def _update_settings(self):
        settings = Settings.get_settings()
        self.max_users = settings.max_users
        self.queue_timeout = settings.queue_timeout
        self.choice_timeout = settings.choice_timeout
        self.max_events = settings.max_events
        print(f"Configurações atualizadas: max_users={self.max_users}, queue_timeout={self.queue_timeout}")
        
    def add_user(self, user_id):
        with self.lock:
            self._update_settings()
            self._clean_expired_queue_users()
            
            if len(self.active_users) < self.max_users:
                self.active_users.add(user_id)
                return True
                
            self.waiting_queue.append(user_id)
            self.user_queue_times[user_id] = datetime.now(UTC)
            return False
            
    def set_user_browser_info(self, user_id, browser_info):
        """Armazena as informações do navegador do usuário"""
        with self.lock:
            self.user_browser_info[user_id] = browser_info
            
    def remove_user(self, user_id):
        with self.lock:
            if user_id in self.active_users:
                self.active_users.remove(user_id)
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
            self.user_queue_times.pop(user_id, None)
            self.user_browser_info.pop(user_id, None)
            
    def _clean_expired_queue_users(self):
        current_time = datetime.now(UTC)
        expired_users = []
        
        for user_id in list(self.waiting_queue):
            queue_time = self.user_queue_times.get(user_id)
            if queue_time:
                elapsed_time = (current_time - queue_time).total_seconds()
                if elapsed_time > self.queue_timeout:
                    expired_users.append(user_id)
                    print(f"Usuário {user_id} removido da fila após {elapsed_time} segundos (timeout: {self.queue_timeout})")
                    socketio.emit('queue_timeout', {
                        'message': 'Seu tempo na fila expirou'
                    }, room=user_id)
        
        for user_id in expired_users:
            self.waiting_queue.remove(user_id)
            self.user_queue_times.pop(user_id, None)
            
        return expired_users
                
    def _process_queue(self):
        self._update_settings()
        self._clean_expired_queue_users()
        
        if self.waiting_queue and len(self.active_users) < self.max_users:
            next_user = self.waiting_queue.popleft()
            self.user_queue_times.pop(next_user, None)
            self.active_users.add(next_user)
            return next_user
        return None
        
    def get_queue_position(self, user_id):
        try:
            return list(self.waiting_queue).index(user_id) + 1
        except ValueError:
            return None
            
    def get_queue_time_remaining(self, user_id):
        queue_time = self.user_queue_times.get(user_id)
        if not queue_time:
            return None
        
        elapsed = (datetime.now(UTC) - queue_time).total_seconds()
        remaining = max(0, self.queue_timeout - elapsed)
        return int(remaining)
        
    def move_to_end_of_queue(self, user_id):
        with self.lock:
            if user_id in self.active_users:
                self.active_users.remove(user_id)
                self.waiting_queue.append(user_id)
                self.user_queue_times[user_id] = datetime.now(UTC)
                
                # Processa o próximo usuário da fila
                next_user = self._process_queue()
                return next_user

    def cleanup_disconnected_users(self):
        """Remove usuários desconectados das listas ativas e da fila"""
        with self.lock:
            # Remove usuários inativos da fila ativa
            for user_id in list(self.active_users):
                try:
                    # Verifica se o usuário ainda está na lista de rooms do socketio
                    if not socketio.server.rooms.get(user_id):
                        print(f"Removendo usuário inativo: {user_id}")
                        self.remove_user(user_id)
                except Exception as e:
                    print(f"Erro ao verificar status do usuário {user_id}: {str(e)}")
            
            # Remove usuários inativos da fila de espera
            for user_id in list(self.waiting_queue):
                try:
                    if not socketio.server.rooms.get(user_id):
                        print(f"Removendo usuário inativo da fila: {user_id}")
                        self.waiting_queue.remove(user_id)
                        self.user_queue_times.pop(user_id, None)
                except Exception as e:
                    print(f"Erro ao verificar status do usuário na fila {user_id}: {str(e)}")

events_manager = EventsManager() 