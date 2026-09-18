import asyncio
import time
import threading

class APIRateLimiter:
    def __init__(self, requests_per_minute: int = 25):
        self.requests_per_minute = requests_per_minute
        self.lock = threading.Lock()
        self.next_allowed_time = time.time()

    async def wait_if_needed(self):
        """Đảm bảo không gọi quá giới hạn req/min trên toàn bộ các luồng (Thread-safe)"""
        if self.requests_per_minute <= 0:
            return
            
        min_interval = 60.0 / self.requests_per_minute
        
        with self.lock:
            now = time.time()
            if self.next_allowed_time < now:
                self.next_allowed_time = now
                
            wake_up_time = self.next_allowed_time
            self.next_allowed_time += min_interval
            
        delay = wake_up_time - time.time()
        if delay > 0:
            await asyncio.sleep(delay)

    def update_rate(self, new_rate: int):
        with self.lock:
            self.requests_per_minute = new_rate

# Khởi tạo một instance toàn cục để dùng chung cho tất cả các worker
global_rate_limiter = APIRateLimiter(requests_per_minute=25)
