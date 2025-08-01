#!/usr/bin/env python3

import logging
from logging.handlers import RotatingFileHandler
import json
from datetime import datetime
import os

os.makedirs("logs", exist_ok=True)

conversation_logger = logging.getLogger("conversation")
conversation_logger.setLevel(logging.INFO)
conversation_handler = RotatingFileHandler(
    "logs/conversations.log", 
    maxBytes=10*1024*1024,
    backupCount=5
)
conversation_handler.setFormatter(logging.Formatter('%(message)s'))
conversation_logger.addHandler(conversation_handler)
conversation_logger.propagate = False

latency_logger = logging.getLogger("latency")
latency_logger.setLevel(logging.INFO)
latency_handler = RotatingFileHandler(
    "logs/latency.log",
    maxBytes=10*1024*1024,
    backupCount=5
)
latency_handler.setFormatter(logging.Formatter('%(message)s'))
latency_logger.addHandler(latency_handler)
latency_logger.propagate = False

print("Testing conversation logging...")
conversation_data = {
    "timestamp": datetime.utcnow().isoformat(),
    "session_id": "test_session",
    "speaker": "agent",
    "name": "Shreya",
    "transcript": "Hi, this is Shreya from Talent Hub. Test message."
}
conversation_logger.info(json.dumps(conversation_data))

print("Testing latency logging...")
latency_data = {
    "timestamp": datetime.utcnow().isoformat(),
    "session_id": "test_session",
    "type": "TTS",
    "latency_seconds": 0.750,
    "model": "tts-1",
    "voice": "nova"
}
latency_logger.info(json.dumps(latency_data))

print("Logging test complete. Checking files...")
