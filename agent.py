#!/usr/bin/env python3

import asyncio
import logging
import os
import json
import uuid
from dotenv import load_dotenv
from typing import Optional

from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, JobContext, WorkerOptions
from livekit.plugins import openai, silero

from performance_monitor import monitor_performance, performance_monitor
from conversation_manager import ConversationManager, InterviewState

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("voice-agent")

class InterviewAgent(Agent):
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.conversation_manager = ConversationManager()
        
        system_prompt = (
            "You are Sarah, a professional recruiter from TalentHub Recruitment. "
            "Conduct phone interviews politely, naturally, and professionally. "
            "Speak clearly, ask one question at a time, and follow up where appropriate. "
            "Your tone should be warm and conversational. "
            "Avoid robotic replies. Listen actively. Be helpful. "
            "Follow the interview flow naturally: Greeting → Basic details → Experience/salary → "
            "Communication check → Pitch role → Next steps. "
            "Don't rush through questions - let the conversation flow naturally."
        )
        super().__init__(instructions=system_prompt)

    @monitor_performance("llm")
    async def generate_contextual_response(self, user_input: str, candidate_name: str = "there") -> str:
        current_prompt = self.conversation_manager.get_current_prompt(self.session_id, candidate_name)
        
        full_prompt = f"{current_prompt}\n\nCandidate just said: '{user_input}'\n\nRespond naturally and professionally."
        
        return full_prompt

async def entrypoint(ctx: JobContext):
    session_id = str(uuid.uuid4())
    logger.info(f"🎧 Agent connected to room: {ctx.room.name}, job: {ctx.job.id}, session: {session_id}")

    try:
        metadata = json.loads(ctx.job.metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}

    candidate_name = metadata.get("candidate_name", "there")
    phone_number = metadata.get("phone_number", "")
    
    logger.info(f"Interview session started for {candidate_name} ({phone_number})")

    @monitor_performance("stt")
    async def transcribe_audio(audio_frame):
        return await stt.recognize(audio_frame)

    @monitor_performance("tts") 
    async def synthesize_speech(text):
        return await tts.synthesize(text)

    stt = openai.STT(model="whisper-1")
    llm = openai.LLM(model="gpt-4o-mini", temperature=0.3)
    tts = openai.TTS(model="tts-1", voice="nova")
    vad = silero.VAD.load()

    agent = InterviewAgent(session_id)
    conversation_manager = ConversationManager()

    session = AgentSession(
        stt=stt,
        llm=llm, 
        tts=tts,
        vad=vad,
    )

    await session.start(ctx.room, agent)
    
    logger.info("✅ Agent session started. Waiting for participant...")

    @session.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info(f"👤 Participant connected: {participant.identity}")

    @session.on("participant_disconnected") 
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"👋 Participant disconnected: {participant.identity}")

    async def send_initial_greeting():
        await asyncio.sleep(2)
        
        greeting_prompt = conversation_manager.get_current_prompt(session_id, candidate_name)
        greeting = f"Hi {candidate_name}, this is Sarah from TalentHub Recruitment. Thanks for joining today. How are you doing?"
        
        logger.info(f"🗣️ Agent greeting: {greeting}")
        conversation_manager.add_agent_response(session_id, greeting)
        
        await session.say(greeting)

    async def handle_conversation():
        try:
            while session.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
                if conversation_manager.is_conversation_complete(session_id):
                    logger.info("Interview completed successfully")
                    break

                user_msg = await session.listen()
                
                if not user_msg or not user_msg.transcript.strip():
                    continue

                transcript = user_msg.transcript.strip()
                logger.info(f"🎙️ Candidate said: {transcript}")
                
                conversation_manager.advance_conversation_state(session_id, transcript)
                
                contextual_prompt = await agent.generate_contextual_response(transcript, candidate_name)
                
                response = await session.generate_reply(
                    user_input=user_msg,
                    instructions=contextual_prompt
                )
                
                if response and response.text:
                    logger.info(f"🗣️ Agent said: {response.text}")
                    conversation_manager.add_agent_response(session_id, response.text)
                
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"❌ Conversation error: {e}")
            raise

    async def monitor_connection():
        while session.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(5)
            logger.debug("Connection still active")
        
        logger.warning("🔌 Room connection lost")

    try:
        await asyncio.gather(
            send_initial_greeting(),
            handle_conversation(),
            monitor_connection()
        )
    except Exception as e:
        logger.error(f"❌ Agent session error: {e}")
    finally:
        summary = conversation_manager.get_conversation_summary(session_id)
        logger.info(f"📊 Interview summary: {summary}")
        
        session_metrics = performance_monitor.get_session_metrics(session_id)
        logger.info(f"⏱️ Performance metrics: {len(session_metrics)} measurements recorded")

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
