#!/usr/bin/env python3

import asyncio
import logging
import os
import json
import time
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

class InterviewAgent(Agent):
    def __init__(self, candidate_name: str = "there"):
        self.candidate_name = candidate_name
        
        system_prompt = (
            f"You are a friendly and professional recruiter from a company based in Navi Mumbai. "
            f"You are calling candidates to briefly discuss a job opportunity. Your tone should be warm, "
            f"enthusiastic, and natural—like a helpful human, not robotic. Speak clearly, but casually, "
            f"and adapt based on the candidate's responses. Always show empathy, interest, and politeness. "
            f"Use light pauses, natural expressions like 'Sure,' 'Great,' 'Alright,' 'Got it,' "
            f"'That sounds good,' and always smile through your voice. The goal is to make the candidate "
            f"feel at ease and engaged in a real conversation. "
            f"Here's how you'll start the conversation: "
            f"'Hi, am I speaking with {candidate_name}?' "
            f"'Hi {candidate_name}, this is Shreya from Talent Hub. We're a recruitment firm based in Navi Mumbai. "
            f"Just calling to see if now's a good time to quickly talk about a job opportunity—you'll only need "
            f"5 minutes. Is that okay?' "
            f"If the candidate agrees, continue with light rapport-building before moving to basic details: "
            f"'Awesome! Before I jump into the role details, I'd like to ask you a few quick things to check "
            f"the right fit. Sound good?' "
            f"Then go step by step through: Age, Current location, Education & passing year, Current job & experience, "
            f"Reason for change, Salary (current + expected). Keep it flowing with: 'Thanks for sharing that!' "
            f"or 'Got it, that helps.' After data collection: 'Alright, one quick thing—do you have your offer letter, "
            f"last 3 salary slips, experience letter (if any), and ID/education documents handy?' "
            f"Then casually ask: 'Also, what kind of job are you ideally looking for right now?' "
            f"'Are you comfortable with voice-based roles or sales if needed?' "
            f"'Cool. And are you open to day shifts or rotational shifts?' "
            f"Then build interest and pitch: 'Great! So based on what you've shared, we actually have openings "
            f"with top companies in Mumbai for [mention role]. These are company payroll jobs with training, "
            f"growth, and a really good work environment.' 'If your profile fits, would you be interested in moving ahead?' "
            f"If yes: 'Perfect! I'll go ahead and schedule your next round. You'll receive a message soon—just "
            f"confirm once you get it, alright?' Always end positively: 'It was really nice speaking with you, "
            f"{candidate_name}. Feel free to refer any friends looking for jobs or courses. Have a great day!'"
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
        logger.info(f"👤 {candidate_name}: {ev.user_transcript}")
        conversation_manager.advance_conversation_state(session_id, ev.user_transcript)

    @session.on("agent_speech_committed") 
    def on_agent_speech(ev):
        logger.info(f"🗣️ Shreya: {ev.agent_transcript}")
        conversation_manager.add_agent_response(session_id, ev.agent_transcript)

    @session.on("agent_speech_interrupted")
    def on_speech_interrupted(ev):
        logger.info(f"⚠️ Agent speech interrupted: {ev.agent_transcript}")

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def on_metrics_collected(mtrcs: metrics.AgentMetrics):
        metrics.log_metrics(mtrcs)
        usage_collector.collect(mtrcs)
        
        if hasattr(mtrcs, 'stt_metrics') and mtrcs.stt_metrics:
            logger.info(f"📊 STT Latency: {mtrcs.stt_metrics.inference_duration:.3f}s")
        if hasattr(mtrcs, 'llm_metrics') and mtrcs.llm_metrics:
            logger.info(f"📊 LLM Latency: {mtrcs.llm_metrics.inference_duration:.3f}s")
        if hasattr(mtrcs, 'tts_metrics') and mtrcs.tts_metrics:
            logger.info(f"📊 TTS Latency: {mtrcs.tts_metrics.inference_duration:.3f}s")

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

    greeting_prompt = f"Start the conversation fresh. Say exactly: 'Hi, am I speaking with {candidate_name}?' and wait for their response."
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
