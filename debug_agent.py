#!/usr/bin/env python3

import asyncio
import logging
import os
import json
from dotenv import load_dotenv

from livekit import agents, rtc
from livekit.agents import JobContext, WorkerOptions
from livekit.plugins import groq, silero

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("debug-agent")

async def debug_entrypoint(ctx: JobContext):
    logger.info(f"🔍 DEBUG: Agent connecting to room: {ctx.room.name}")
    logger.info(f"🔍 DEBUG: Job metadata: {ctx.job.metadata}")
    
    try:
        metadata = json.loads(ctx.job.metadata or "{}")
        logger.info(f"🔍 DEBUG: Parsed metadata: {metadata}")
    except json.JSONDecodeError as e:
        logger.error(f"🔍 DEBUG: Failed to parse metadata: {e}")
        metadata = {}

    candidate_name = metadata.get("candidate_name", "there")
    phone_number = metadata.get("phone_number", "")
    
    logger.info(f"🔍 DEBUG: Candidate: {candidate_name}, Phone: {phone_number}")
    
    try:
        logger.info("🔍 DEBUG: Testing Groq STT initialization...")
        stt = groq.STT(model="whisper-large-v3-turbo", language="en")
        logger.info("✅ DEBUG: Groq STT initialized successfully")
        
        logger.info("🔍 DEBUG: Testing Groq LLM initialization...")
        llm = groq.LLM(model="llama3-8b-8192", temperature=0.7)
        logger.info("✅ DEBUG: Groq LLM initialized successfully")
        
        logger.info("🔍 DEBUG: Testing Groq TTS initialization...")
        tts = groq.TTS(model="playai-tts", voice="Fritz-PlayAI")
        logger.info("✅ DEBUG: Groq TTS initialized successfully")
        
        logger.info("🔍 DEBUG: Testing Silero VAD initialization...")
        vad = silero.VAD.load()
        logger.info("✅ DEBUG: Silero VAD initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ DEBUG: Error initializing Groq services: {e}")
        raise
    
    logger.info("🔍 DEBUG: All services initialized, connecting to room...")
    await ctx.connect()
    logger.info("✅ DEBUG: Connected to room successfully")
    
    logger.info("🔍 DEBUG: Agent is ready and waiting...")
    
    while True:
        await asyncio.sleep(1)

def main():
    required_vars = [
        "GROQ_API_KEY", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "LIVEKIT_URL"
    ]
    for var in required_vars:
        if not os.getenv(var):
            logger.error(f"Missing environment variable: {var}")
            return

    logger.info("🔍 DEBUG: Starting debug agent...")
    
    worker_options = WorkerOptions(
        entrypoint_fnc=debug_entrypoint,
        agent_name=os.getenv("LIVEKIT_AGENT_NAME", "recruiter-agent")
    )
    
    agents.cli.run_app(worker_options)

if __name__ == "__main__":
    main()
