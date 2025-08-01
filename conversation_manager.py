import json
import logging
import redis
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger("conversation_manager")

class InterviewState(Enum):
    GREETING = "greeting"
    BASIC_DETAILS = "basic_details"
    DOCUMENTS_CHECK = "documents_check"
    COMMUNICATION_ASSESSMENT = "communication_assessment"
    ROLE_PITCH = "role_pitch"
    NEXT_STEPS = "next_steps"
    COMPLETED = "completed"

class ConversationManager:
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        try:
            self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
            self.redis_client.ping()
            self.redis_enabled = True
            logger.info("Redis connected for conversation management")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory storage: {e}")
            self.redis_enabled = False
            self.conversation_cache = {}
        
        self.interview_prompts = {
            InterviewState.GREETING: {
                "system": "You are Sarah, a warm and professional recruiter from TalentHub Recruitment. Start with a friendly greeting and confirm you're speaking with the right person. Ask if it's a good time to speak for 5 minutes about a job opportunity.",
                "questions": [
                    "Hi, am I speaking with {candidate_name}?",
                    "Hi {candidate_name}, this is Sarah calling from TalentHub Recruitment, we are a recruitment firm based in Vashi, Navi Mumbai.",
                    "Is this a good time to speak for 5 minutes about a job opportunity that might interest you?"
                ]
            },
            InterviewState.BASIC_DETAILS: {
                "system": "Collect basic details naturally through conversation. Ask about age, location, education, experience, and salary expectations. Don't ask all questions at once - let the conversation flow naturally.",
                "questions": [
                    "I'd like to quickly understand a few details to check the right fit for our current openings.",
                    "May I know your age?",
                    "Which area are you currently staying in?",
                    "What is your highest qualification?",
                    "Are you currently working? If yes, where and what's your role?",
                    "What is your current salary and what are your expectations?"
                ]
            },
            InterviewState.DOCUMENTS_CHECK: {
                "system": "Ask about required documents in a conversational way. Don't sound like you're reading from a checklist.",
                "questions": [
                    "Do you have your offer letter, recent salary slips, and other documents ready?",
                    "We'll need some basic documents for the process - offer letter, last 3 months salary slips, and ID proof. Do you have these available?"
                ]
            },
            InterviewState.COMMUNICATION_ASSESSMENT: {
                "system": "Assess communication skills naturally by asking open-ended questions about their job preferences and work style.",
                "questions": [
                    "Can you briefly tell me about the kind of job you're looking for?",
                    "Are you comfortable working in voice-based processes or sales roles if required?",
                    "Are you open to rotational shifts or day shifts based on the job requirements?"
                ]
            },
            InterviewState.ROLE_PITCH: {
                "system": "Build interest by pitching relevant roles based on what they've shared. Be enthusiastic but professional.",
                "questions": [
                    "Based on what you've shared, we have openings in customer support and sales roles with top companies in Mumbai.",
                    "These are direct company payroll jobs with a good work environment, training, and growth opportunities.",
                    "Would you be interested in taking this ahead if your profile matches?"
                ]
            },
            InterviewState.NEXT_STEPS: {
                "system": "Wrap up positively and explain next steps. Make sure they know what to expect.",
                "questions": [
                    "Perfect, I'll schedule you for the next round.",
                    "You'll receive a message shortly with interview details. Please confirm once you get it.",
                    "All the best, {candidate_name}, and thank you for your time!"
                ]
            }
        }

    def get_session_key(self, session_id: str) -> str:
        return f"conversation:{session_id}"

    def save_conversation_state(self, session_id: str, state: Dict[str, Any]):
        state['last_updated'] = datetime.utcnow().isoformat()
        
        if self.redis_enabled:
            try:
                key = self.get_session_key(session_id)
                self.redis_client.setex(key, 3600, json.dumps(state))
            except Exception as e:
                logger.error(f"Failed to save conversation state to Redis: {e}")
        else:
            self.conversation_cache[session_id] = state

    def load_conversation_state(self, session_id: str) -> Dict[str, Any]:
        if self.redis_enabled:
            try:
                key = self.get_session_key(session_id)
                data = self.redis_client.get(key)
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Failed to load conversation state from Redis: {e}")
        else:
            return self.conversation_cache.get(session_id, {})
        
        return self.create_new_conversation_state()

    def create_new_conversation_state(self) -> Dict[str, Any]:
        return {
            "current_state": InterviewState.GREETING.value,
            "candidate_info": {},
            "conversation_history": [],
            "questions_asked": [],
            "responses_received": [],
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": datetime.utcnow().isoformat()
        }

    def get_current_prompt(self, session_id: str, candidate_name: str = "there") -> str:
        state = self.load_conversation_state(session_id)
        current_state = InterviewState(state.get("current_state", InterviewState.GREETING.value))
        
        prompts = self.interview_prompts[current_state]
        system_prompt = prompts["system"]
        
        questions_asked = set(state.get("questions_asked", []))
        available_questions = [q for q in prompts["questions"] if q not in questions_asked]
        
        if available_questions:
            next_question = available_questions[0].format(candidate_name=candidate_name)
            state["questions_asked"].append(available_questions[0])
            self.save_conversation_state(session_id, state)
            return f"{system_prompt}\n\nNext question to ask: {next_question}"
        else:
            return f"{system_prompt}\n\nContinue the conversation naturally based on their responses."

    def advance_conversation_state(self, session_id: str, user_response: str):
        state = self.load_conversation_state(session_id)
        current_state = InterviewState(state.get("current_state", InterviewState.GREETING.value))
        
        state["responses_received"].append({
            "state": current_state.value,
            "response": user_response,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        state["conversation_history"].append({
            "role": "user",
            "content": user_response,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        questions_asked_in_state = len([q for q in state.get("questions_asked", []) 
                                      if any(q in prompt for prompt in self.interview_prompts[current_state]["questions"])])
        
        should_advance = (
            questions_asked_in_state >= len(self.interview_prompts[current_state]["questions"]) - 1 or
            self._should_advance_based_on_response(current_state, user_response)
        )
        
        if should_advance:
            next_state = self._get_next_state(current_state)
            if next_state:
                state["current_state"] = next_state.value
                logger.info(f"Advanced conversation from {current_state.value} to {next_state.value}")
        
        self.save_conversation_state(session_id, state)
        return state

    def _should_advance_based_on_response(self, current_state: InterviewState, response: str) -> bool:
        response_lower = response.lower()
        
        if current_state == InterviewState.GREETING:
            return any(word in response_lower for word in ["yes", "sure", "okay", "good time", "go ahead"])
        elif current_state == InterviewState.ROLE_PITCH:
            return any(word in response_lower for word in ["yes", "interested", "sure", "sounds good"])
        
        return False

    def _get_next_state(self, current_state: InterviewState) -> Optional[InterviewState]:
        state_order = [
            InterviewState.GREETING,
            InterviewState.BASIC_DETAILS,
            InterviewState.DOCUMENTS_CHECK,
            InterviewState.COMMUNICATION_ASSESSMENT,
            InterviewState.ROLE_PITCH,
            InterviewState.NEXT_STEPS,
            InterviewState.COMPLETED
        ]
        
        try:
            current_index = state_order.index(current_state)
            if current_index < len(state_order) - 1:
                return state_order[current_index + 1]
        except ValueError:
            pass
        
        return None

    def add_agent_response(self, session_id: str, response: str):
        state = self.load_conversation_state(session_id)
        state["conversation_history"].append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.utcnow().isoformat()
        })
        self.save_conversation_state(session_id, state)

    def is_conversation_complete(self, session_id: str) -> bool:
        state = self.load_conversation_state(session_id)
        return state.get("current_state") == InterviewState.COMPLETED.value

    def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        state = self.load_conversation_state(session_id)
        return {
            "session_id": session_id,
            "current_state": state.get("current_state"),
            "candidate_info": state.get("candidate_info", {}),
            "total_exchanges": len(state.get("conversation_history", [])),
            "duration": self._calculate_duration(state),
            "completion_status": "completed" if self.is_conversation_complete(session_id) else "in_progress"
        }

    def _calculate_duration(self, state: Dict[str, Any]) -> Optional[str]:
        created_at = state.get("created_at")
        last_updated = state.get("last_updated")
        
        if created_at and last_updated:
            try:
                start = datetime.fromisoformat(created_at)
                end = datetime.fromisoformat(last_updated)
                duration = end - start
                return str(duration)
            except Exception:
                pass
        
        return None
