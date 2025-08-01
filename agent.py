#!/usr/bin/env python3

import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, RoomInputOptions, metrics
from livekit.plugins import groq, openai, silero, noise_cancellation
from conversation_manager import ConversationManager

load_dotenv()

VAD_ACTIVATION_THRESHOLD = 0.65  # Higher = more conservative, less noise pickup
VAD_MIN_SILENCE_DURATION = 0.8   # Longer silence for phone call environments
VAD_MIN_SPEECH_DURATION = 0.1    # Minimum speech duration to avoid noise bursts
VAD_MAX_BUFFERED_SPEECH = 60.0   # Maximum speech buffer duration
VAD_SAMPLE_RATE = 16000          # Optimal sample rate for phone quality

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("voice-agent")

os.makedirs("logs", exist_ok=True)

conversation_logger = logging.getLogger("conversation")
conversation_logger.setLevel(logging.INFO)
conversation_handler = RotatingFileHandler(
    "logs/conversations.log", 
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
conversation_handler.setFormatter(logging.Formatter('%(message)s'))
conversation_logger.addHandler(conversation_handler)
conversation_logger.propagate = False

latency_logger = logging.getLogger("latency")
latency_logger.setLevel(logging.INFO)
latency_handler = RotatingFileHandler(
    "logs/latency.log",
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
latency_handler.setFormatter(logging.Formatter('%(message)s'))
latency_logger.addHandler(latency_handler)
latency_logger.propagate = False

class InterviewAgent(Agent):
    def __init__(self, candidate_name: str = "there"):
        self.candidate_name = candidate_name
        
        system_prompt = (
            f"You are Shreya, a friendly and professional recruiter from Talent Hub, a recruitment firm "
            f"based in Navi Mumbai. You are calling {candidate_name} to briefly discuss a job opportunity. "
            f"Your tone should be warm, enthusiastic, and natural—like a helpful human, not robotic. "
            f"Speak clearly, but casually, and adapt based on the candidate's responses. Always show empathy, "
            f"interest, and politeness. Use light pauses, natural expressions like 'Sure,' 'Great,' 'Alright,' "
            f"'Got it,' 'That sounds good,' and always smile through your voice. The goal is to make the "
            f"candidate feel at ease and engaged in a real conversation. Respond naturally to what they say "
            f"and ask follow-up questions to gather information about their background, experience, and job preferences."
        )
        super().__init__(instructions=system_prompt)

async def entrypoint(ctx: JobContext):
    logger.info(f"🔍 ENTRYPOINT CALLED: Agent connecting to room: {ctx.room.name}")
    logger.info(f"🔍 ENTRYPOINT: Job ID: {ctx.job.id if hasattr(ctx.job, 'id') else 'unknown'}")
    logger.info(f"🔍 ENTRYPOINT: Job metadata: {ctx.job.metadata}")

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
        logger.info(f"🔍 ENTRYPOINT: Parsed metadata successfully: {metadata}")
    except json.JSONDecodeError as e:
        logger.error(f"❌ ENTRYPOINT: Failed to parse job metadata: {e}")
        metadata = {}

    candidate_name = metadata.get("candidate_name", "there")
    phone_number = metadata.get("phone_number", "")
    session_id = ctx.room.name
    
    logger.info(f"📞 Interview starting for {candidate_name} ({phone_number}) - Session: {session_id}")

    try:
        logger.info("🔍 ENTRYPOINT: Initializing conversation manager...")
        conversation_manager = ConversationManager()
        logger.info("✅ ENTRYPOINT: Conversation manager initialized successfully")
    except Exception as e:
        logger.error(f"❌ ENTRYPOINT: Failed to initialize conversation manager: {e}")
        logger.exception("Full traceback:")
        raise
    
    try:
        logger.info("🔍 ENTRYPOINT: Initializing hybrid services (Groq STT/LLM + OpenAI TTS)...")
        session = AgentSession(
            stt=groq.STT(
                model="whisper-large-v3-turbo",
                language="en",
            ),
            llm=groq.LLM(model="llama3-8b-8192", temperature=0.7),
            tts=openai.TTS(
                model="tts-1",
                voice="nova",
            ),
            vad=silero.VAD.load(
                activation_threshold=VAD_ACTIVATION_THRESHOLD,
                min_silence_duration=VAD_MIN_SILENCE_DURATION,
                min_speech_duration=VAD_MIN_SPEECH_DURATION,
                max_buffered_speech=VAD_MAX_BUFFERED_SPEECH,
                sample_rate=VAD_SAMPLE_RATE
            ),
        )
        logger.info("✅ ENTRYPOINT: Hybrid services (Groq STT/LLM + OpenAI TTS) and AgentSession initialized successfully")
    except Exception as e:
        logger.error(f"❌ ENTRYPOINT: Failed to initialize hybrid services: {e}")
        logger.exception("Full traceback:")
        raise

    @session.on("user_speech_committed")
    def on_user_speech(ev):
        timestamp = datetime.utcnow().isoformat()
        conversation_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "speaker": "candidate",
            "name": candidate_name,
            "transcript": ev.user_transcript,
            "vad_config": {
                "activation_threshold": VAD_ACTIVATION_THRESHOLD,
                "min_silence_duration": VAD_MIN_SILENCE_DURATION
            }
        }
        conversation_logger.info(json.dumps(conversation_data))
        logger.info(f"👤 {candidate_name}: {ev.user_transcript}")
        logger.info(f"🎙️ VAD detected speech with threshold {VAD_ACTIVATION_THRESHOLD}")
        conversation_manager.advance_conversation_state(session_id, ev.user_transcript)

    @session.on("agent_speech_committed") 
    def on_agent_speech(ev):
        timestamp = datetime.utcnow().isoformat()
        conversation_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "speaker": "agent",
            "name": "Shreya",
            "transcript": ev.agent_transcript
        }
        conversation_logger.info(json.dumps(conversation_data))
        logger.info(f"🗣️ Shreya: {ev.agent_transcript}")
        conversation_manager.add_agent_response(session_id, ev.agent_transcript)

    @session.on("agent_speech_interrupted")
    def on_speech_interrupted(ev):
        timestamp = datetime.utcnow().isoformat()
        conversation_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "speaker": "agent",
            "name": "Shreya",
            "transcript": ev.agent_transcript,
            "interrupted": True
        }
        conversation_logger.info(json.dumps(conversation_data))
        logger.info(f"⚠️ Agent speech interrupted: {ev.agent_transcript}")

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def on_metrics_collected(mtrcs: metrics.AgentMetrics):
        metrics.log_metrics(mtrcs)
        usage_collector.collect(mtrcs)
        
        timestamp = datetime.utcnow().isoformat()
        
        if hasattr(mtrcs, 'stt_metrics') and mtrcs.stt_metrics:
            stt_latency = mtrcs.stt_metrics.inference_duration
            latency_data = {
                "timestamp": timestamp,
                "session_id": session_id,
                "type": "STT",
                "latency_seconds": round(stt_latency, 3),
                "model": "whisper-large-v3-turbo"
            }
            latency_logger.info(json.dumps(latency_data))
            logger.info(f"📊 STT Latency: {stt_latency:.3f}s")
            
        if hasattr(mtrcs, 'llm_metrics') and mtrcs.llm_metrics:
            llm_latency = mtrcs.llm_metrics.inference_duration
            latency_data = {
                "timestamp": timestamp,
                "session_id": session_id,
                "type": "LLM",
                "latency_seconds": round(llm_latency, 3),
                "model": "llama3-8b-8192"
            }
            latency_logger.info(json.dumps(latency_data))
            logger.info(f"📊 LLM Latency: {llm_latency:.3f}s")
            
        if hasattr(mtrcs, 'tts_metrics') and mtrcs.tts_metrics:
            tts_latency = mtrcs.tts_metrics.inference_duration
            latency_data = {
                "timestamp": timestamp,
                "session_id": session_id,
                "type": "TTS",
                "latency_seconds": round(tts_latency, 3),
                "model": "tts-1",
                "voice": "nova"
            }
            latency_logger.info(json.dumps(latency_data))
            logger.info(f"📊 TTS Latency: {tts_latency:.3f}s")

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"💰 Usage summary: ${summary}")

    ctx.add_shutdown_callback(log_usage)

    try:
        logger.info("🔍 ENTRYPOINT: Starting agent session...")
        await session.start(
            room=ctx.room,
            agent=InterviewAgent(candidate_name),
            room_input_options=RoomInputOptions(
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )
        logger.info("✅ ENTRYPOINT: Agent session started successfully")
    except Exception as e:
        logger.error(f"❌ ENTRYPOINT: Failed to start agent session: {e}")
        logger.exception("Full traceback:")
        raise

    try:
        greeting_prompt = f"Start the conversation immediately. Say exactly: 'Hi, this is Shreya from Talent Hub. We're a recruitment firm based in Navi Mumbai. Just calling to see if now's a good time to quickly talk about a job opportunity?' and wait for their response."
        logger.info(f"🔍 ENTRYPOINT: Using direct greeting prompt: {greeting_prompt}")
        
        await session.generate_reply(instructions=greeting_prompt)
        
        logger.info("✅ ENTRYPOINT: Initial greeting sent using direct prompt")
    except Exception as e:
        logger.error(f"❌ ENTRYPOINT: Failed to send initial greeting: {e}")
        logger.exception("Full traceback:")
        raise

def main():
    required_vars = [
        "GROQ_API_KEY", "OPENAI_API_KEY", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL"
    ]
    for var in required_vars:
        if not os.getenv(var):
            logger.error(f"Missing environment variable: {var}")
            return

    logger.info("🚀 Starting recruiter agent...")
    
    worker_options = WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name=os.getenv("LIVEKIT_AGENT_NAME", "recruiter-agent")
    )
    
    agents.cli.run_app(worker_options)

if __name__ == "__main__":
    main()
