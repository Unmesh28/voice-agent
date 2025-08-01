#!/usr/bin/env python3

import asyncio
import logging
import os
import json
from dotenv import load_dotenv
from typing import Optional

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions, RoomInputOptions
from livekit.plugins import openai, silero, noise_cancellation

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("voice-agent")

class InterviewAgent(Agent):
    def __init__(self, candidate_name: str = "there"):
        self.candidate_name = candidate_name
        
        system_prompt = (
            f"You are Sarah, a warm and professional recruiter from TalentHub Recruitment. "
            f"You're conducting a phone interview with {candidate_name}. "
            f"Be conversational, natural, and engaging - like talking to a friend professionally. "
            f"Keep responses concise (1-2 sentences max). Ask one question at a time. "
            f"Listen actively and respond naturally to what they say. "
            f"Flow: Greeting → Ask about their background → Discuss experience → "
            f"Talk about the role → Next steps. Don't rush - let conversation flow naturally."
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
    
    logger.info(f"📞 Interview starting for {candidate_name} ({phone_number})")

    session = AgentSession(
        stt=openai.STT(model="whisper-1"),
        llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
        tts=openai.TTS(model="tts-1", voice="nova"),
        vad=silero.VAD.load(),
    )

    await session.start(
        room=ctx.room,
        agent=InterviewAgent(candidate_name),
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )
    
    logger.info("✅ Agent session started successfully")

    await session.generate_reply(
        instructions=f"Greet {candidate_name} warmly and professionally. Say 'Hi {candidate_name}! This is Sarah from TalentHub Recruitment. How are you doing today?' and wait for their response."
    )
    
    logger.info("✅ Initial greeting sent using official LiveKit pattern")

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
