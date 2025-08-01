#!/usr/bin/env python3

import asyncio
import json
import os
import sys
import subprocess
import logging
import requests
from typing import Dict, Optional, Union
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cloud-call-manager")

class CloudCallManager:
    def __init__(self):
        self.livekit_url = os.getenv("LIVEKIT_URL")
        self.api_key = os.getenv("LIVEKIT_API_KEY")
        self.api_secret = os.getenv("LIVEKIT_API_SECRET")
        self.agent_name = os.getenv("LIVEKIT_AGENT_NAME", "recruiter-agent")
        self.sip_domain = os.getenv("TWILIO_SIP_DOMAIN")

        if not all([self.livekit_url, self.api_key, self.api_secret, self.sip_domain]):
            raise ValueError("LiveKit Cloud credentials and SIP domain are required")

        self.api_base_url = self.livekit_url.replace("wss://", "https://").replace("ws://", "http://")

    def create_call_metadata(self, candidate_name: str, phone_number: str) -> str:
        timestamp = datetime.now().isoformat()
        return json.dumps({
            "candidate_name": candidate_name,
            "phone_number": phone_number,
            "timestamp": timestamp,
            "call_type": "interview",
            "platform": "livekit_cloud"
        })

    def dispatch_agent_to_room(self, room_name: str, metadata_json: str) -> bool:
        try:
            cmd = [
                "lk",
                "--url", self.livekit_url,
                "--api-key", self.api_key,
                "--api-secret", self.api_secret,
                "dispatch", "create",
                "--room", room_name,
                "--agent-name", self.agent_name,
                "--metadata", metadata_json
            ]

            logger.info(f"Dispatching agent to room: {room_name}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

            if result.returncode == 0:
                logger.info("Agent dispatched successfully")
                return True
            else:
                logger.error(f"Dispatch failed: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Error dispatching agent: {e}")
            return False

    async def place_sip_call(self, room_name: str, candidate_name: str, phone_number: str, trunk_id: str) -> bool:
        metadata_json = self.create_call_metadata(candidate_name, phone_number)
        call_request = {
            "sip_trunk_id": trunk_id,
            "sip_call_to": phone_number,
            "room_name": room_name,
            "participant_identity": f"candidate_{candidate_name.lower().replace(' ', '_')}",
            "participant_name": candidate_name,
            "participant_metadata": metadata_json,
            "play_dialtone": True,
            "hide_phone_number": False,
            "wait_until_answered": True
        }

        with open("/tmp/sip_call.json", "w") as f:
            json.dump(call_request, f, indent=2)

        cmd = [
            "lk",
            "--url", self.livekit_url,
            "--api-key", self.api_key,
            "--api-secret", self.api_secret,
            "sip", "participant", "create",
            "/tmp/sip_call.json"
        ]

        logger.info("Placing SIP call...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            logger.info("Call placed successfully")
            return True
        else:
            logger.error(f"Failed to place call: {result.stderr}")
            return False

    async def initiate_interview(self, candidate_name: str, phone_number: str, trunk_id: str):
        logger.info(f"Initiating interview for {candidate_name} at {phone_number}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        room_name = f"interview_{candidate_name.lower().replace(' ', '_')}_{timestamp}"
        metadata_json = self.create_call_metadata(candidate_name, phone_number)

        dispatched = self.dispatch_agent_to_room(room_name, metadata_json)
        if not dispatched:
            logger.error("Agent dispatch failed")
            return False

        await asyncio.sleep(3)
        return await self.place_sip_call(room_name, candidate_name, phone_number, trunk_id)

def main():
    required_vars = [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
        "TWILIO_SIP_TRUNK_ID", "OPENAI_API_KEY", "TWILIO_SIP_DOMAIN"
    ]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    call_mgr = CloudCallManager()
    print("\n📞 LiveKit Cloud Recruiter Bot")
    print("="*50)

    candidate = input("Candidate name: ").strip()
    phone = input("Phone number (with +91...): ").strip()
    if not phone.startswith('+'):
        phone = '+' + phone

    confirm = input(f"Call {candidate} at {phone}? (y/N): ").strip().lower()
    if confirm != 'y':
        sys.exit(0)

    async def run():
        success = await call_mgr.initiate_interview(candidate, phone, os.getenv("TWILIO_SIP_TRUNK_ID"))
        print("\n✅ Done" if success else "\n❌ Failed")

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted")

if __name__ == "__main__":
    main()
