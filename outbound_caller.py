#!/usr/bin/env python3

import asyncio
import json
import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Optional
from call_manager import CloudCallManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("outbound-caller")

class OutboundCaller:
    def __init__(self):
        self.call_manager = CloudCallManager()
        self.trunk_id = os.getenv("TWILIO_SIP_TRUNK_ID")
        
        if not self.trunk_id:
            raise ValueError("TWILIO_SIP_TRUNK_ID environment variable is required")

    async def make_single_call(self, candidate_name: str, phone_number: str) -> bool:
        logger.info(f"🔄 Starting outbound call to {candidate_name} at {phone_number}")
        
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number
            logger.info(f"Added country code: {phone_number}")
        
        try:
            success = await self.call_manager.initiate_interview(
                candidate_name, phone_number, self.trunk_id
            )
            
            if success:
                logger.info(f"✅ Call to {candidate_name} initiated successfully")
                logger.info("The AI interviewer agent will:")
                logger.info("  1. Join the call automatically")
                logger.info("  2. Greet the candidate warmly")
                logger.info("  3. Conduct the interview following the script")
                logger.info("  4. Collect all required information")
                logger.info("  5. Provide next steps")
                return True
            else:
                logger.error(f"❌ Failed to initiate call to {candidate_name}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error calling {candidate_name}: {e}")
            return False

    async def make_batch_calls(self, candidates: List[Dict[str, str]], delay_between_calls: int = 30):
        logger.info(f"🚀 Starting batch outbound calling for {len(candidates)} candidates")
        logger.info(f"Delay between calls: {delay_between_calls} seconds")
        
        results = []
        
        for i, candidate in enumerate(candidates, 1):
            name = candidate.get('name', f'Candidate_{i}')
            phone = candidate.get('phone', '')
            
            if not phone:
                logger.warning(f"⚠️ Skipping {name} - no phone number provided")
                results.append({'name': name, 'phone': phone, 'status': 'skipped', 'reason': 'no_phone'})
                continue
            
            logger.info(f"📞 [{i}/{len(candidates)}] Calling {name}...")
            
            success = await self.make_single_call(name, phone)
            status = 'success' if success else 'failed'
            results.append({'name': name, 'phone': phone, 'status': status})
            
            if i < len(candidates):
                logger.info(f"⏳ Waiting {delay_between_calls} seconds before next call...")
                await asyncio.sleep(delay_between_calls)
        
        self.print_batch_summary(results)
        return results

    def print_batch_summary(self, results: List[Dict]):
        logger.info("\n" + "="*60)
        logger.info("📊 BATCH CALLING SUMMARY")
        logger.info("="*60)
        
        successful = [r for r in results if r['status'] == 'success']
        failed = [r for r in results if r['status'] == 'failed']
        skipped = [r for r in results if r['status'] == 'skipped']
        
        logger.info(f"✅ Successful calls: {len(successful)}")
        logger.info(f"❌ Failed calls: {len(failed)}")
        logger.info(f"⚠️ Skipped calls: {len(skipped)}")
        logger.info(f"📞 Total attempted: {len(results)}")
        
        if successful:
            logger.info("\n✅ SUCCESSFUL CALLS:")
            for result in successful:
                logger.info(f"  • {result['name']} ({result['phone']})")
        
        if failed:
            logger.info("\n❌ FAILED CALLS:")
            for result in failed:
                logger.info(f"  • {result['name']} ({result['phone']})")
        
        if skipped:
            logger.info("\n⚠️ SKIPPED CALLS:")
            for result in skipped:
                logger.info(f"  • {result['name']} - {result.get('reason', 'unknown')}")

def load_candidates_from_file(file_path: str) -> List[Dict[str, str]]:
    try:
        with open(file_path, 'r') as f:
            if file_path.endswith('.json'):
                return json.load(f)
            else:
                candidates = []
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split(',')
                    if len(parts) >= 2:
                        candidates.append({
                            'name': parts[0].strip(),
                            'phone': parts[1].strip()
                        })
                    else:
                        logger.warning(f"Invalid format on line {line_num}: {line}")
                
                return candidates
    except Exception as e:
        logger.error(f"Error loading candidates from {file_path}: {e}")
        return []

def main():
    required_vars = [
        "LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET",
        "TWILIO_SIP_TRUNK_ID", "OPENAI_API_KEY", "TWILIO_SIP_DOMAIN"
    ]
    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        logger.error(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    caller = OutboundCaller()
    
    print("\n📞 AI Interviewer - Outbound Calling System")
    print("="*60)
    print("This system will:")
    print("• Place outbound calls to candidates")
    print("• AI agent joins automatically")
    print("• Conducts structured interviews")
    print("• Monitors performance and logs metrics")
    print("="*60)
    
    mode = input("\nSelect mode:\n1. Single call\n2. Batch calls from file\n3. Batch calls manual entry\nChoice (1-3): ").strip()
    
    async def run_single():
        candidate = input("Candidate name: ").strip()
        phone = input("Phone number (with country code): ").strip()
        
        if not phone.startswith('+'):
            phone = '+' + phone
        
        confirm = input(f"\n📞 Call {candidate} at {phone}? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Call cancelled")
            return
        
        success = await caller.make_single_call(candidate, phone)
        if success:
            print(f"\n✅ Call initiated! The AI agent will interview {candidate}")
            print("💡 Monitor the LiveKit dashboard for call status")
        else:
            print(f"\n❌ Failed to initiate call to {candidate}")

    async def run_batch_file():
        file_path = input("Enter path to candidates file (JSON or CSV): ").strip()
        
        if not os.path.exists(file_path):
            print(f"❌ File not found: {file_path}")
            return
        
        candidates = load_candidates_from_file(file_path)
        if not candidates:
            print("❌ No valid candidates found in file")
            return
        
        print(f"\n📋 Found {len(candidates)} candidates:")
        for i, candidate in enumerate(candidates[:5], 1):
            print(f"  {i}. {candidate['name']} - {candidate['phone']}")
        
        if len(candidates) > 5:
            print(f"  ... and {len(candidates) - 5} more")
        
        delay = input(f"\nDelay between calls (default 30 seconds): ").strip()
        delay = int(delay) if delay.isdigit() else 30
        
        confirm = input(f"\n📞 Start batch calling {len(candidates)} candidates? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Batch calling cancelled")
            return
        
        await caller.make_batch_calls(candidates, delay)

    async def run_batch_manual():
        candidates = []
        print("\nEnter candidates (press Enter with empty name to finish):")
        
        while True:
            name = input(f"Candidate {len(candidates) + 1} name: ").strip()
            if not name:
                break
            
            phone = input(f"Phone number for {name}: ").strip()
            if not phone:
                print("⚠️ Skipping candidate without phone number")
                continue
            
            candidates.append({'name': name, 'phone': phone})
            print(f"✅ Added {name}")
        
        if not candidates:
            print("❌ No candidates entered")
            return
        
        delay = input(f"\nDelay between calls (default 30 seconds): ").strip()
        delay = int(delay) if delay.isdigit() else 30
        
        confirm = input(f"\n📞 Start calling {len(candidates)} candidates? (y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ Batch calling cancelled")
            return
        
        await caller.make_batch_calls(candidates, delay)

    try:
        if mode == '1':
            asyncio.run(run_single())
        elif mode == '2':
            asyncio.run(run_batch_file())
        elif mode == '3':
            asyncio.run(run_batch_manual())
        else:
            print("❌ Invalid choice")
    except KeyboardInterrupt:
        print("\n⏹️ Interrupted by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
