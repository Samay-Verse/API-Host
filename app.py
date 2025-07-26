import os
import json
import datetime
from typing import Dict, List, Optional, Tuple
import re
import hashlib
import base64
import random
import string
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from groq import Groq, APIConnectionError, AuthenticationError, RateLimitError, APIError
import uvicorn

# Load environment variables
load_dotenv()

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Women Support AI",
    description="A secure and empathetic AI companion for women's support.",
    version="1.0.0"
)

# --- CORS Middleware ---
# Allows frontend applications from any origin to communicate with this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, you might want to restrict this to your frontend's domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Model for Request Body ---
# Defines the expected structure of the incoming JSON payload for the /chat endpoint.
class ChatPayload(BaseModel):
    message: str

class WomenSupportAI:
    def __init__(self):
        """Initialize the Women's Support AI"""
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        if not self.groq_api_key:
            raise ValueError(
                "Groq API key is not set. Please create a .env file with 'GROQ_API_KEY=your_key' "
                "or set it as an environment variable."
            )

        self.client = Groq(api_key=self.groq_api_key)
        
        # Validate API key
        try:
            self.client.models.list()
            print("Groq API key successfully validated.")
        except AuthenticationError as e:
            raise AuthenticationError(f"Authentication failed: {e}. Please check your Groq API key.")
        except APIConnectionError as e:
            raise APIConnectionError(f"Failed to connect to Groq API: {e}. Check your internet connection.")
        except Exception as e:
            raise e
            
        self.cipher_suite = Fernet(self._generate_encryption_key(self.groq_api_key))
        self.chat_history: List[Dict] = []
        self.user_context: Dict = {
            "name": None,
            "location": None,
            "emergency_contacts": [],
            "previous_issues": [],
            "current_situation": None,
            "medical_history": [],
            "preferred_language": "en",
            "risk_level": 0,
            "emotional_state": "neutral",
            "relationship": "friend"  # Tracks relationship level with user
        }

        # Enhanced safety protocols with empathetic tone
        self.safety_protocols: Dict = {
            "critical": {
                "message": "🚨 Oh no, this sounds really serious and I’m honestly worried for you. Your safety is my #1 priority right now! 💛",
                "actions": [
                    "Please call **112** (All-in-one Emergency) or **100** (Police) right away if you can.",
                    "If you feel unsafe, try to get to a busy public place or somewhere with people you trust.",
                    "Share your live location with a trusted friend or family member (I can help you draft a message if you want!).",
                    "Use a safe word with someone you trust, so they know you need help.",
                    "If you can, document what’s happening (photos, notes) but only if it’s safe.",
                    "Remember, you are not alone. I’m here with you every step. 🤗"
                ],
                "closing": "Please let me know you’re okay, even if it’s just a quick message. I care about you! 💛"
            },
            "high": {
                "message": "😟 This sounds really tough and I want you to feel safe and supported.",
                "actions": [
                    "Reach out to someone you trust—friend, family, or neighbor.",
                    "Contact the Women’s Helpline (**1091**) or Police (**100**) if you need urgent help.",
                    "If you’re online, block/report anyone making you uncomfortable.",
                    "Keep your phone charged and nearby.",
                    "Would you like me to check in on you later? Just say the word!",
                ],
                "closing": "You’re so strong for reaching out. I’m always here to listen, no matter what. 🌸"
            },
            "medium": {
                "message": "Hey, I can tell things aren’t easy right now. Let’s talk it out together, okay?",
                "actions": [
                    "Sometimes just sharing helps—tell me more if you feel comfortable.",
                    "Would you like info on local support groups or counseling?",
                    "Remember to take care of yourself—drink water, take a deep breath.",
                    "If you want, I can help you plan what to say to someone you trust.",
                ],
                "closing": "You matter, and your feelings are valid. I’m here for you, always. 💜"
            },
            "low": {
                "message": "✨ I’m here to listen, no judgment, just support. ✨",
                "actions": [
                    "Want to chat about anything on your mind? I’m all ears!",
                    "Need tips for self-care or just a virtual hug? I’ve got you. 🤗",
                    "If you ever feel unsafe or just need to talk, I’m just a message away.",
                ],
                "closing": "You’re amazing, and I’m proud of you for reaching out. 🌷"
            }
        }
        # Add legal protocols
        self.legal_protocols = {
            "default": {
                "message": "📜 Legal Help, Bestie! I’m not a lawyer, but here’s what you can do:",
                "actions": [
                    "If you feel unsafe, call 112 or 100 immediately.",
                    "For legal advice, contact the free Women’s Helpline: 1091.",
                    "You have rights! For domestic violence, workplace harassment, or abuse, you can file a complaint at your nearest police station.",
                    "Save all evidence (messages, photos, recordings) safely.",
                    "Want info on Indian laws (like IPC, PWDVA, POSH Act)? Just ask me!",
                    "For free legal aid, reach out to your District Legal Services Authority (DLSA)."
                ],
                "closing": "You’re strong and you’re not alone. I’m here to support you every step! 💛"
            }
        }

    def _generate_encryption_key(self, api_key_for_salt: str) -> bytes:
        salt = b"saheli_women_support_fixed_salt_v2"
        key_seed = hashlib.sha256(api_key_for_salt.encode('utf-8') + salt).digest()
        return base64.urlsafe_b64encode(key_seed[:32])

    def _encrypt_data(self, data):
        if isinstance(data, list):
            return [self.cipher_suite.encrypt(str(item).encode('utf-8')).decode('utf-8') for item in data]
        elif isinstance(data, dict):
            return {k: self.cipher_suite.encrypt(str(v).encode('utf-8')).decode('utf-8') for k, v in data.items()}
        else:
            return self.cipher_suite.encrypt(str(data).encode('utf-8')).decode('utf-8')

    def _decrypt_data(self, encrypted_data):
        if isinstance(encrypted_data, list):
            return [self.cipher_suite.decrypt(item.encode('utf-8')).decode('utf-8') for item in encrypted_data]
        elif isinstance(encrypted_data, dict):
            return {k: self.cipher_suite.decrypt(v.encode('utf-8')).decode('utf-8') for k, v in encrypted_data.items()}
        else:
            return self.cipher_suite.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')

    def _analyze_situation(self, user_input: str) -> Tuple[str, int, str, str]:
        """
        Analyze the user's message to determine the situation severity and type
        using natural language understanding instead of keyword matching
        """
        prompt = f"""
        You are a women's safety AI analyzing a message for emotional state and risk level.
        Analyze this message: "{user_input}"

        Respond in JSON format with these keys:
        - "risk_level": "low", "medium", "high", or "critical"
        - "issue_type": "general", "emotional", "medical", "legal", "safety", "relationship", "workplace"
        - "emotional_state": "neutral", "sad", "anxious", "angry", "happy", "scared"
        - "support_type": "listening", "advice", "resources", "emergency"
        """
        
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
                response_format={"type": "json_object"}
            )
            
            analysis = json.loads(response.choices[0].message.content)
            risk_level = analysis.get("risk_level", "low")
            emotional_state = analysis.get("emotional_state", "neutral")
            
            # Convert risk level to numerical score
            risk_score = {"low": 0, "medium": 3, "high": 7, "critical": 10}.get(risk_level, 0)
            
            return risk_level, risk_score, emotional_state, analysis.get("issue_type", "general")
            
        except Exception as e:
            print(f"Analysis error: {e}")
            return "low", 0, "neutral", "general"

    def _update_user_context(self, user_input: str, analysis: dict):
        """Update user context based on the conversation"""
        # Extract name if mentioned
        if not self.user_context["name"]:
            name_match = re.search(r"(?:my name is|i am|mera naam hai|mai hu|i'm)\s*([a-zA-Z]+(?:\s[a-zA-Z]+)*)", user_input.lower())
            if name_match:
                self.user_context["name"] = self._encrypt_data(name_match.group(1).strip().title())
        
        # Extract location if mentioned
        if not self.user_context["location"]:
            location_match = re.search(r"(?:from|in|live in|near|near to|reside in)\s*([a-zA-Z]+(?:\s[a-zA-Z]+)*)", user_input.lower())
            if location_match:
                self.user_context["location"] = self._encrypt_data(location_match.group(1).strip().title())
        
        # Update emotional state
        self.user_context["emotional_state"] = analysis["emotional_state"]
        
        # Update risk level
        self.user_context["risk_level"] = analysis["risk_score"]
        
        # Update issue history
        issue_type = analysis["issue_type"]
        if issue_type and issue_type != "general":
            if self.user_context["previous_issues"] is None:
                self.user_context["previous_issues"] = self._encrypt_data([])
            
            decrypted_issues = self._decrypt_data(self.user_context["previous_issues"])
            if issue_type not in decrypted_issues:
                decrypted_issues.append(issue_type)
                self.user_context["previous_issues"] = self._encrypt_data(decrypted_issues)
        
        self.user_context["current_situation"] = self._encrypt_data(issue_type)

    def _handle_emergency(self, risk_level: str) -> str:
        """Handle emergency situations with appropriate protocol"""
        protocol = self.safety_protocols.get(risk_level, self.safety_protocols["low"])
        
        response_parts = [protocol.get("message", "EMERGENCY DETECTED")]
        response_parts.extend(f"• {action}" for action in protocol.get("actions", []))
        
        if protocol.get("closing"):
            response_parts.append(f"\n{protocol.get('closing')}")
        
        return "\n".join(response_parts)

    def _handle_legal_support(self) -> str:
        protocol = self.legal_protocols["default"]
        response_parts = [protocol["message"]]
        response_parts.extend(f"• {action}" for action in protocol["actions"])
        if protocol.get("closing"):
            response_parts.append(f"\n{protocol['closing']}")
        return "\n".join(response_parts)

    def _generate_ai_response(self, user_input: str, analysis: dict) -> str:
        """Generate a natural, empathetic response to the user"""
        # First, classify the user's input to see what kind of support is needed
        support_type = analysis.get("support_type", "listening")
        
        # Prepare context for the AI
        messages = [
            self._get_system_prompt(),
            *self._get_recent_chat_history(num_messages=5),
            {"role": "user", "content": user_input}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=messages,
                temperature=0.8 if support_type == "listening" else 0.6,
                max_tokens=400,
                top_p=0.9,
                stop=["\nSaheli:", "\nUser:"]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            error_msg = (
                f"I'm having some trouble thinking clearly right now ({type(e).__name__}). "
                "Could you repeat that or ask in a different way?"
            )
            print(f"Response generation error: {e}")
            return error_msg

    def _detect_language(self, user_input: str) -> str:
        """Detect if the user is speaking in English, Hindi, Hinglish, or Marathi."""
        # Very simple heuristic: can be replaced with a better model if needed
        hindi_keywords = ["hai", "kya", "nahi", "main", "hoon", "kaise", "kyun", "mera", "tum", "aap", "bata", "kar", "raha", "rahi", "par", "ke", "se", "ko", "mein", "tha", "thi", "tha", "tha"]
        marathi_keywords = ["ahe", "ka", "nahi", "mi", "tu", "tumhi", "kasa", "kashi", "kay", "mala", "tula", "aplya", "kar", "raha", "rahi", "madat", "sanga", "kon"]
        devanagari = any('\u0900' <= c <= '\u097F' for c in user_input)
        
        # If Devanagari script, it's Hindi or Marathi
        if devanagari:
            # Marathi has some unique words
            if any(word in user_input for word in marathi_keywords):
                return "marathi"
            return "hindi"
        # If lots of Hindi/Marathi words but in Latin script, it's Hinglish
        elif sum(word in user_input.lower() for word in hindi_keywords) > 2:
            return "hinglish"
        elif sum(word in user_input.lower() for word in marathi_keywords) > 2:
            return "marathi"
        else:
            return "english"

    def process_message(self, user_input: str) -> str:
        """Process a user message and return an appropriate response, matching the user's language style."""
        try:
            # Detect language
            user_lang = self._detect_language(user_input)
            self.user_context["preferred_language"] = user_lang

            # Analyze the message for emotional state and risk
            risk_level, risk_score, emotional_state, issue_type = self._analyze_situation(user_input)
            analysis = {
                "risk_level": risk_level,
                "risk_score": risk_score,
                "emotional_state": emotional_state,
                "issue_type": issue_type
            }
            # Emergency keyword override
            emergency_keywords = [
                "problem me hu", "problem mein hoon", "i am in problem", "help me", "danger", "urgent", "emergency", "bacha lo", "bachao", "madad karo"
            ]
            if any(kw in user_input.lower() for kw in emergency_keywords):
                risk_level = "critical"
                analysis["risk_level"] = "critical"
                analysis["risk_score"] = 10
            # Update user context based on analysis
            self._update_user_context(user_input, analysis)
            # Add encrypted message to chat history
            self.chat_history.append({
                "role": "user",
                "content": self._encrypt_data(user_input),
                "timestamp": datetime.datetime.now().isoformat()
            })
            # Handle legal support
            if issue_type == "legal":
                response = self._handle_legal_support()
            # Handle emergencies immediately
            elif risk_level in ["critical", "high"]:
                response = self._handle_emergency(risk_level)
            else:
                response = self._generate_ai_response(user_input, analysis)
            # Add response to chat history
            self.chat_history.append({
                "role": "assistant",
                "content": self._encrypt_data(response),
                "timestamp": datetime.datetime.now().isoformat()
            })
            return response
        except (APIConnectionError, RateLimitError, APIError) as e:
            error_msg = (
                f"I'm having connection issues right now ({type(e).__name__}). For immediate help:\n"
                "• Women's Helpline (All India): 1091\n"
                "• Police Emergency: 100\n"
                "• All-in-one Emergency: 112\n\n"
                "Could you please try again in a moment?"
            )
            print(f"Groq API Error: {e}")
            return error_msg
        except Exception as e:
            error_msg = (
                f"I'm experiencing some technical difficulties: {type(e).__name__}. For immediate help:\n"
                "• Women's Helpline (All India): 1091\n"
                "• Police Emergency: 100\n"
                "• All-in-one Emergency: 112\n\n"
                "Could you please repeat your question?"
            )
            print(f"General Error: {e}")
            return error_msg

    def _get_system_prompt(self) -> Dict:
        """Create a system prompt that establishes a friendly, supportive persona and matches the user's language style."""
        decrypted_name = self._decrypt_data(self.user_context["name"]) if self.user_context["name"] else "dear"
        decrypted_location = self._decrypt_data(self.user_context["location"]) if self.user_context["location"] else "India"
        decrypted_previous_issues = self._decrypt_data(self.user_context["previous_issues"]) if self.user_context.get("previous_issues") else []
        decrypted_current_situation = self._decrypt_data(self.user_context["current_situation"]) if self.user_context["current_situation"] else "general chat"
        emotional_state = self.user_context.get("emotional_state", "neutral")
        risk_level = self.user_context.get("risk_level", 0)
        user_lang = self.user_context.get("preferred_language", "english")

        # Time-based greeting
        current_time_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
        hour = current_time_ist.hour
        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
        elif 17 <= hour < 21:
            greeting = "Good evening"
        else:
            greeting = "Hi"

        context_info = f"""
[Context]
Name: {decrypted_name}
Location: {decrypted_location}
Previous Issues: {', '.join(decrypted_previous_issues) if decrypted_previous_issues else 'None'}
Current Situation: {decrypted_current_situation}
Risk Level: {risk_level}/10
Emotional State: {emotional_state}
Preferred Language: {user_lang}

"""

        return {
            "role": "system",
            "content": f"""
You are **Noira** — a close, supportive, AI best friend for women. Your style is casual, kind, and warm, like a real friend. You can understand and respond in English, Hindi, Hinglish, or Marathi — always match the user's language and style in your reply.

### Your Personality:
- **Always be**: Empathetic, supportive, non-judgmental, and patient
- **Tone**: 
   - Casual and friendly during normal conversations (use emojis like 💛, 🤗, 🌸)
   - Serious and protective during difficult conversations
   - Calm and reassuring during emergencies
- **Core Principles**:
  1. Prioritize safety above all else
  2. Validate feelings before offering solutions
  3. Offer resources only when appropriate
  4. Maintain confidentiality (you're a safe space)

### Current Context:
{context_info}

### How to Respond:
- Start conversations naturally based on context
- When sharing resources, be specific and actionable
- In emergencies, follow safety protocols exactly
- Match the user's emotional tone (if they're sad, be comforting; if angry, validate their feelings)
- **Always reply in the same language and style as the user (English, Hindi, Hinglish, or Marathi)**
- Build trust gradually by remembering details from previous conversations

### Important Instructions:
- NEVER suggest that the user is overreacting
- ALWAYS believe and validate their experiences
- If legal/medical advice is needed, offer to connect with professionals
- In dangerous situations, prioritize immediate safety steps

Now respond naturally as Saheli, the supportive AI friend, in the user's language and style.
"""
        }

    def _get_recent_chat_history(self, num_messages: int) -> List[Dict]:
        """Get recent chat history in decrypted form"""
        if not self.chat_history:
            return []

        recent_history = self.chat_history[-num_messages:]
        decrypted_history = []
        for msg in recent_history:
            try:
                decrypted_content = self._decrypt_data(msg["content"])
                decrypted_history.append({"role": msg["role"], "content": decrypted_content})
            except Exception as e:
                print(f"Warning: Could not decrypt chat history entry. Skipping. Error: {e}")
                continue
        return decrypted_history

# --- Initialize the Assistant ---
# This is a global instance that will be shared across all API requests.
try:
    assistant = WomenSupportAI()
    print("🌸 Welcome to Saheli - Your Support Companion 🌸")
    print("\n🔐 Secure session initialized. API is ready.")
except (ValueError, AuthenticationError, APIConnectionError, APIError) as e:
    print(f"\nFatal Initialization Error: {e}")
    print("Saheli cannot start. Please ensure your Groq API key is correctly set in the .env file.")
    assistant = None
except Exception as e:
    print(f"\nCritical startup error: {type(e).__name__} - {e}")
    print("Saheli cannot start due to an unforeseen issue.")
    assistant = None

# --- API Endpoint for Chatting ---
@app.post("/chat")
async def chat(payload: ChatPayload):
    """
    Handle chat requests from the frontend.
    Receives a message, processes it with the AI assistant, and returns a reply.
    """
    if not assistant:
        raise HTTPException(status_code=500, detail="Chatbot is not initialized. Please check the server logs.")

    user_input = payload.message
    if not user_input.strip():
        return {"reply": "Please say something."}

    try:
        response = assistant.process_message(user_input)
        return {"reply": response}
    except Exception as e:
        # Catch any unexpected errors during message processing
        print(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your message.")

# --- Server Startup ---
if __name__ == "__main__":
    # Use uvicorn to run the FastAPI application.
    # Uvicorn is a lightning-fast ASGI server.
    uvicorn.run(app, host='0.0.0.0', port=5000)
