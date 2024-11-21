from threading import Lock
from collections import deque
from datetime import datetime, timedelta
from app import db
from app.models import Settings

class EventsManager:
    def __init__(self):
        self.active_users = set()
        self.waiting_queue = deque()
        self.user_queue_times = {}  # Armazena quando cada usuário entrou na fila
        self.lock = Lock()
        self._update_settings()
        
    def _update_settings(self):
        settings = Settings.get_settings()
        self.max_users = settings.max_users
        self.queue_timeout = settings.queue_timeout
        self.choice_timeout = settings.choice_timeout
        self.max_events = settings.max_events
        
    def add_user(self, user_id):
        with self.lock:
            self._update_settings()
            self._clean_expired_queue_users()
            
            if len(self.active_users) < self.max_users:
                self.active_users.add(user_id)
                return True
                
            self.waiting_queue.append(user_id)
            self.user_queue_times[user_id] = datetime.utcnow()
            return False
            
    def remove_user(self, user_id):
        with self.lock:
            if user_id in self.active_users:
                self.active_users.remove(user_id)
                next_user = self._process_queue()
                return next_user
            if user_id in self.waiting_queue:
                self.waiting_queue.remove(user_id)
                self.user_queue_times.pop(user_id, None)
                
    def _clean_expired_queue_users(self):
        """Remove usuários que excederam o tempo limite na fila"""
        current_time = datetime.utcnow()
        expired_users = []
        
        for user_id in list(self.waiting_queue):
            queue_time = self.user_queue_times.get(user_id)
            if queue_time and (current_time - queue_time).total_seconds() > self.queue_timeout:
                expired_users.append(user_id)
                
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
        
        elapsed = (datetime.utcnow() - queue_time).total_seconds()
        remaining = max(0, self.queue_timeout - elapsed)
        return int(remaining)

events_manager = EventsManager() 