# Voice Agent Interviewer

A real-time AI interviewer that automatically joins calls and conducts dynamic interviews using OpenAI's TTS, STT, and LLM services with LiveKit Cloud integration.

## Features

- **Real-time Voice Interaction**: Uses OpenAI Whisper (STT), GPT-4o-mini (LLM), and TTS-1 with nova voice
- **Dynamic Interview Flow**: Follows structured interview stages while maintaining natural conversation
- **Performance Monitoring**: Tracks response times for STT, LLM, and TTS processes
- **Redis Caching**: Optimizes performance and maintains conversation state
- **Call Stability**: Implements connection monitoring and recovery mechanisms
- **LiveKit Cloud Integration**: Seamless SIP calling through Twilio integration

## Interview Flow

1. **Greeting**: Warm introduction and confirmation
2. **Basic Details**: Age, location, education, experience, salary expectations
3. **Documents Check**: Required documents verification
4. **Communication Assessment**: Open-ended questions to assess communication skills
5. **Role Pitch**: Present relevant opportunities based on candidate profile
6. **Next Steps**: Schedule follow-up and provide clear instructions

## Setup

### Prerequisites

- Python 3.9 or later
- Redis server (optional, falls back to in-memory storage)
- LiveKit CLI (`lk` command)

### Installation

1. Clone and setup:
```bash
cd voice-agent-project
pip install -r requirements.txt
```

2. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your actual credentials
```

3. Start Redis (optional):
```bash
redis-server
```

### Environment Variables

```bash
# LiveKit Cloud Configuration
LIVEKIT_URL=wss://your-livekit-url
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret
LIVEKIT_AGENT_NAME=recruiter-agent

# Twilio SIP Configuration
TWILIO_SIP_DOMAIN=your-sip-domain
TWILIO_SIP_TRUNK_ID=your-trunk-id

# OpenAI Configuration
OPENAI_API_KEY=your-openai-key

# Redis Configuration (Optional)
REDIS_HOST=localhost
REDIS_PORT=6379
```

## Usage

### Running the Agent

Start the voice agent:
```bash
python agent.py
```

### Making Test Calls

Use the call manager to initiate interviews:
```bash
python call_manager.py
```

### Console Testing

Test the agent locally without SIP:
```bash
python agent.py console
```

## Architecture

### Core Components

- **`agent.py`**: Main voice agent with OpenAI integration
- **`call_manager.py`**: Handles SIP calling and room management
- **`conversation_manager.py`**: Manages interview flow and state
- **`performance_monitor.py`**: Tracks and logs performance metrics

### Performance Monitoring

The system tracks:
- STT processing time
- LLM response generation time
- TTS synthesis time
- Conversation flow progression
- Call quality metrics

Metrics are stored in Redis with session-based organization and daily aggregation.

### Conversation State Management

Uses Redis to maintain:
- Current interview stage
- Candidate information collected
- Conversation history
- Questions asked and responses received
- Session recovery data

## Testing

### Local Testing

1. Test agent functionality:
```bash
python agent.py console
```

2. Test call placement:
```bash
python call_manager.py
```

3. Monitor performance:
```bash
# Check Redis for metrics
redis-cli keys "metrics:*"
```

### Production Testing

1. Deploy agent to LiveKit Cloud
2. Configure SIP trunk with Twilio
3. Place test calls to verify:
   - Agent joins calls automatically
   - Greeting is delivered promptly
   - Interview flow progresses naturally
   - Performance metrics are captured
   - Calls remain stable throughout

## Troubleshooting

### Common Issues

1. **Agent not joining calls**:
   - Check LiveKit credentials
   - Verify agent dispatch command
   - Check room creation

2. **Audio quality issues**:
   - Verify OpenAI API key
   - Check network connectivity
   - Monitor performance metrics

3. **Redis connection issues**:
   - System falls back to in-memory storage
   - Check Redis server status
   - Verify connection parameters

### Logs

Monitor logs for detailed information:
```bash
tail -f agent.log
```

Key log patterns:
- `🎧 Agent connected`: Successful room join
- `🗣️ Agent said`: TTS output
- `🎙️ Candidate said`: STT input
- `⏱️ Performance`: Timing metrics
- `❌ Error`: Issues requiring attention

## Version Compatibility

- LiveKit Agents: ~1.0
- Python: 3.9+
- OpenAI API: Latest
- Redis: 6.0+

## Performance Optimization

- Uses Redis for caching and state management
- Implements connection pooling
- Monitors and logs response times
- Optimizes conversation flow transitions
- Implements proper error handling and recovery
