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
from livekit.plugins import openai, silero, noise_cancellation
from conversation_manager import ConversationManager

load_dotenv()

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
    logger.info(f"🎧 Agent connecting to room: {ctx.room.name}")

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}

    candidate_name = metadata.get("candidate_name", "there")
    phone_number = metadata.get("phone_number", "")
    session_id = ctx.room.name
    
    logger.info(f"📞 Interview starting for {candidate_name} ({phone_number}) - Session: {session_id}")

    conversation_manager = ConversationManager()
    
    session = AgentSession(
        stt=openai.STT(model="whisper-1"),
        llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
        tts=openai.TTS(model="tts-1", voice="nova"),
        vad=silero.VAD.load(),
    )

    @session.on("user_speech_committed")
    def on_user_speech(ev):
        timestamp = datetime.utcnow().isoformat()
        conversation_data = {
            "timestamp": timestamp,
            "session_id": session_id,
            "speaker": "candidate",
            "name": candidate_name,
            "transcript": ev.user_transcript
        }
        conversation_logger.info(json.dumps(conversation_data))
        logger.info(f"👤 {candidate_name}: {ev.user_transcript}")
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
                "model": "whisper-1"
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
                "model": "gpt-4o-mini"
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

    await session.start(
        room=ctx.room,
        agent=InterviewAgent(candidate_name),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )
    
    logger.info("✅ Agent session started successfully")

    greeting_prompt = f"Start the conversation immediately. Say exactly: 'Hi, this is Shreya from Talent Hub. We're a recruitment firm based in Navi Mumbai. Just calling to see if now's a good time to quickly talk about a job opportunity?' and wait for their response."
    logger.info(f"📝 Using direct greeting prompt: {greeting_prompt}")
    
    await session.generate_reply(instructions=greeting_prompt)
    
    logger.info("✅ Initial greeting sent using direct prompt")

def main():
    required_vars = [
        "OPENAI_API_KEY", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL"
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
