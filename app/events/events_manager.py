from threading import Lock
from collections import deque
from datetime import datetime, timedelta

class EventsManager:
    def __init__(self, max_users=3):
        self.max_users = max_users
        self.active_users = set()
        self.waiting_queue = deque()
        self.lock = Lock()
        
    def add_user(self, user_id):
        with self.lock:
            if len(self.active_users) < self.max_users:
                self.active_users.add(user_id)
                return True
            self.waiting_queue.append(user_id)
            return False
            
    def remove_user(self, user_id):
        with self.lock:
            if user_id in self.active_users:
                self.active_users.remove(user_id)
                self._process_queue()
                
    def _process_queue(self):
        if self.waiting_queue and len(self.active_users) < self.max_users:
            next_user = self.waiting_queue.popleft()
            self.active_users.add(next_user)
            return next_user
        return None

events_manager = EventsManager() 