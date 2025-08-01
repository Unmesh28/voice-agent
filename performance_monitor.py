import time
import logging
import asyncio
from functools import wraps
from typing import Dict, Any, Optional
import redis
import json
from datetime import datetime

logger = logging.getLogger("performance_monitor")

class PerformanceMonitor:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        try:
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            self.redis_client.ping()
            self.redis_enabled = True
            logger.info("Redis connected for performance monitoring")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory storage: {e}")
            self.redis_enabled = False
            self.metrics_cache = {}

    def log_metric(self, metric_type: str, duration: float, session_id: str, additional_data: Optional[Dict] = None):
        timestamp = datetime.utcnow().isoformat()
        metric_data = {
            "type": metric_type,
            "duration_ms": round(duration * 1000, 2),
            "timestamp": timestamp,
            "session_id": session_id,
            **(additional_data or {})
        }
        
        logger.info(f"Performance [{metric_type}]: {metric_data['duration_ms']}ms")
        
        if self.redis_enabled:
            try:
                key = f"metrics:{session_id}:{metric_type}:{timestamp}"
                self.redis_client.setex(key, 3600, json.dumps(metric_data))
                
                daily_key = f"daily_metrics:{datetime.utcnow().strftime('%Y-%m-%d')}:{metric_type}"
                self.redis_client.lpush(daily_key, json.dumps(metric_data))
                self.redis_client.expire(daily_key, 86400 * 7)
            except Exception as e:
                logger.error(f"Failed to store metric in Redis: {e}")
        else:
            if session_id not in self.metrics_cache:
                self.metrics_cache[session_id] = []
            self.metrics_cache[session_id].append(metric_data)

    def get_session_metrics(self, session_id: str) -> list:
        if self.redis_enabled:
            try:
                pattern = f"metrics:{session_id}:*"
                keys = self.redis_client.keys(pattern)
                metrics = []
                for key in keys:
                    data = self.redis_client.get(key)
                    if data:
                        metrics.append(json.loads(data))
                return sorted(metrics, key=lambda x: x['timestamp'])
            except Exception as e:
                logger.error(f"Failed to retrieve metrics from Redis: {e}")
                return []
        else:
            return self.metrics_cache.get(session_id, [])

performance_monitor = PerformanceMonitor()

def monitor_performance(metric_type: str):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                session_id = getattr(args[0], 'session_id', 'unknown') if args else 'unknown'
                additional_data = {}
                
                if hasattr(result, '__len__') and metric_type == 'tts':
                    additional_data['text_length'] = len(str(result))
                elif hasattr(result, 'text') and metric_type == 'stt':
                    additional_data['transcript_length'] = len(result.text)
                elif hasattr(result, 'text') and metric_type == 'llm':
                    additional_data['response_length'] = len(result.text)
                
                performance_monitor.log_metric(metric_type, duration, session_id, additional_data)
                return result
            except Exception as e:
                duration = time.time() - start_time
                session_id = getattr(args[0], 'session_id', 'unknown') if args else 'unknown'
                performance_monitor.log_metric(f"{metric_type}_error", duration, session_id, {"error": str(e)})
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                session_id = getattr(args[0], 'session_id', 'unknown') if args else 'unknown'
                performance_monitor.log_metric(metric_type, duration, session_id)
                return result
            except Exception as e:
                duration = time.time() - start_time
                session_id = getattr(args[0], 'session_id', 'unknown') if args else 'unknown'
                performance_monitor.log_metric(f"{metric_type}_error", duration, session_id, {"error": str(e)})
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator
