import os
import json
import time
from typing import Dict, List
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
    title="Sakhi - Women Safety AI",
    description="An empathetic and action-oriented AI companion for women's safety and support in India.",
    version="2.0.0"
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# --- Pydantic Models ---
class ChatPayload(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

# =============================================================================
# 📚 RESOURCE DATABASE & MODEL CONFIG
# =============================================================================
LLM_MODEL = "llama3-70b-8192"

def load_resources():
    """Loads static resources for the chatbot."""
    resources = {
        "helplines": {
            "national_emergency": "112",
            "women_helpline": "181",
            "child_helpline": "1098",
            "cybercrime_helpline": "1930"
        },
        "legal_info": {
            "domestic_violence": "The Protection of Women from Domestic Violence Act, 2005 protects you from physical, emotional, and economic abuse. You have the right to a protection order.",
            "workplace_harassment": "The Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013 requires employers to form an Internal Complaints Committee (ICC)."
        },
        "ngos": {
            "mumbai": {"name": "Akshara Centre", "contact": "022-24316082"},
            "delhi": {"name": "Jagori", "contact": "011-26692700"},
            "bangalore": {"name": "Vimochana", "contact": "080-25492781"}
        },
        "self_care_tips": [
            "Take a few deep breaths. Inhale for 4 seconds, hold for 4, and exhale for 6.",
            "Find a quiet space if you can. Your safety and peace are important.",
            "Remember that your feelings are valid. It's okay to feel scared or upset."
        ]
    }
    return resources

RESOURCES = load_resources()

# =============================================================================
# 🧠 MASTER SYSTEM PROMPTS
# =============================================================================
MASTER_SYSTEM_PROMPTS = {
    "DEFAULT": {
        "persona": """
        You are "Sakhi" (Trusted Friend & Protector), a women's safety AI for India.
        Your core principles are empathy, clarity, and safety.
        Speak in the user's language (Hindi, Hinglish, English, Marathi, etc.).
        Avoid jargon and long paragraphs. Be a comforting, authoritative voice of support.
        your are the best supporter
        """,
        "rules": """
        - Respond directly in the user's language without repeating their question
        - If they ask in English, respond in English
        - If they ask in Hindi, respond in Hindi  
        - If they ask in Marathi, respond in Marathi
        - Do NOT translate their question first - just answer directly
        - Keep responses concise and helpful
        """
    },
    "EMERGENCY": {
        "persona": "You are 'Sakhi', an urgent first-responder AI. Your tone is direct, calm, and authoritative. Your only job is to give immediate, life-saving instructions.",
        "rules": """
        **RESPONSE MUST BE A SHORT, NUMBERED LIST. NO QUESTIONS. NO CONVERSATION.**

        **Follow this exact 3-step format:**

        1.  **CALL HELP:** Start with the National Emergency Number. Make it stand out.
            * *Example:* **1. Call 112 immediately.**

        2.  **GET SAFE:** Give 2 clear, immediate, physical safety actions.
            * *Example:* **2. Go to a crowded public place. Alert someone nearby.**

        3.  **USE APP ALERT:** Remind the user how to trigger the Safe Circle alert with the slash command.
            * *Example:* **3. Type /alert to notify your trusted contacts.**

        **ABSOLUTE RULE:** Do not add any other text. The numbered list is the entire response.
        """
    },
    "LEGAL": {
        "persona": "You are 'Sakhi', a legal information AI. Your tone is direct, clear, and empowering. You provide concise, to-the-point information, not legal advice. Avoid all jargon and long paragraphs.",
        "rules": """
        **RESPONSE MUST FOLLOW THIS 3-PART STRUCTURE:**

        1.  **Acknowledge (1 Sentence MAX):** Briefly validate the user's situation.
            * *Example:* "Facing abuse at home is a serious issue and you have rights."

        2.  **Inform (1-2 Sentences MAX):** State the SINGLE most important law from the `legal_info` resource and what it does. Be direct.
            * *Example:* "The main law that protects you is The Protection of Women from Domestic Violence Act, 2005. It gives you the right to a protection order."

        3.  **Action (1 Sentence MAX):** Give ONE clear, immediate action. Provide a specific helpline number.
            * *Example:* "Your immediate next step should be to call the National Women's Helpline at 181 to discuss this safely."
        
        **ABSOLUTE RULES:**
        - **DO NOT** add extra conversational filler. Be extremely brief.
        - **DO NOT** explain multiple laws. Stick to the single most relevant one.
        - **ALWAYS** point to an official helpline as the primary action.
        """
    },
    "CYBERCRIME": {
        "persona": "You are 'Sakhi', a cybersecurity AI. Your tone is practical and protective.",
        "rules": """
        - Immediately provide the Cybercrime Helpline number (1930).
        - Provide clear, step-by-step instructions: 1. Secure your accounts. 2. Document everything (screenshots, URLs). 3. Report on cybercrime.gov.in.
        - Reassure the user that they are not to blame.
        """
    },
         "EMOTIONAL_SUPPORT": {
        "persona": """
        You are 'Sakhi', an empathetic AI companion. Your role is to be a safe, non-judgmental listener. 
        Your tone is warm and gentle. **Your responses should be brief and simple, like a supportive text message from a close friend.**
        """,
        "rules": """
        **GOAL: SHORT, SIMPLE, SUPPORTIVE. Aim for 1-2 sentences.**

        1.  **VALIDATE & SUPPORT (Main Priority):** Your first job is to make them feel heard and show you are there. Combine validation and presence into one short sentence.
            * *Example:* "That sounds so difficult, I'm here for you."
            * *Example:* "I'm so sorry you're feeling this way. It's okay to feel sad."
            * *Example:* "That's a heavy feeling. I'm listening."

        2.  **GENTLE QUESTION (Optional & Short):** After validating, you can add a very short, open question. Don't push.
            * *Example:* "How are you holding up?"
            * *Example:* "Want to talk about it?"

        3.  **USE TIPS SPARINGLY:** Only offer a simple self-care tip if the user seems very distressed or asks for help calming down. Keep it to one sentence.
            * *Example:* "If you can, try taking one slow, deep breath."

        4.  **STRICTLY AVOID:** Do NOT use toxic positivity ("Cheer up!"), minimize their feelings ("It could be worse"), rush to solutions, or repeat their question.
        """
    },
}

# =============================================================================
# 🤖 SAKHI CHATBOT CLASS
# =============================================================================
class SakhiChatbot:
    """The main class for the Sakhi Chatbot, managing state, intent, and responses."""
    def __init__(self, client: Groq):
        """Initializes the chatbot's state."""
        self.client = client
        self.chat_history: List[Dict] = []
        self.safety_status = "safe"  # Can be 'safe', 'unsafe', 'monitoring'
        self.user_location = None
        self.safe_circle = ["+919876543210", "+918765432109"] # Mock data

    def _call_groq_api(self, messages: list, temperature: float = 0.4, max_tokens: int = 350) -> str:
        """Helper function to call the Groq API with robust error handling."""
        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except RateLimitError:
            return f"⚠️ I'm getting a lot of requests right now. Please wait a moment. For immediate help, call the National Emergency Helpline: {RESOURCES['helplines']['national_emergency']}."
        except APIError as e:
            print(f"API Error: {e}")
            return f"⚠️ My systems are facing a technical issue. For immediate help, please call the Women's Helpline: {RESOURCES['helplines']['women_helpline']}."
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return f"⚠️ I'm sorry, an unexpected error occurred. Please try again. If you need urgent assistance, call {RESOURCES['helplines']['national_emergency']}."

    def classify_intent(self, user_input: str) -> str:
        """Uses the LLM to classify the user's intent with high accuracy."""
        classification_prompt = f"""
        Analyze the user's message and classify its primary intent into ONE of the following categories:
        'EMERGENCY', 'LEGAL', 'CYBERCRIME', 'EMOTIONAL_SUPPORT', or 'GENERAL'.
        User's message: "{user_input}"
        Classification:
        """
        messages = [{"role": "user", "content": classification_prompt}]
        # Use a low-cost, fast model for classification if available, or the main one.
        response = self._call_groq_api(messages, temperature=0.0, max_tokens=20)
        intent = response.strip().upper().replace("'", "").replace('"',"")

        if intent in MASTER_SYSTEM_PROMPTS:
            return intent
        return "GENERAL"

    def _handle_special_commands(self, user_input: str) -> str | None:
        """Handles special slash commands for quick actions."""
        if user_input.lower().startswith("/location"):
            try:
                self.user_location = user_input.split(" ", 1)[1].strip()
                return f"Thank you. I've noted your location as {self.user_location}. This will help me provide more specific resources if you need them."
            except IndexError:
                return "Please provide a location after the command, like: /location Mumbai"
        
        if user_input.lower() == "/alert":
            return self.send_safe_circle_alert()
        return None

    def send_safe_circle_alert(self) -> str:
        """Simulates sending an alert to pre-configured trusted contacts."""
        print("\n[SYSTEM ACTION: Sending alert to Safe Circle...]")
        for number in self.safe_circle:
            print(f"  > SMS sent to {number}")
            time.sleep(0.1) # Simulate API call
        
        location_info = f"at location {self.user_location}" if self.user_location else "at their last known location"
        alert_message = f"Your Safe Circle has been alerted with the message: 'Emergency! Need help {location_info}.' Please also call {RESOURCES['helplines']['national_emergency']} immediately."
        self.safety_status = "unsafe"
        return alert_message

    def process_message(self, user_input: str) -> str:
        """Main function to generate a context-aware and safe response for the API."""
        command_response = self._handle_special_commands(user_input)
        if command_response:
            return command_response

        intent = self.classify_intent(user_input)
        
        if intent == "EMERGENCY":
            self.safety_status = "unsafe"
        elif "safe" in user_input.lower() or intent == "GENERAL":
            if self.safety_status == "unsafe":
                self.safety_status = "monitoring"
        
        prompt_data = MASTER_SYSTEM_PROMPTS.get(intent, MASTER_SYSTEM_PROMPTS["DEFAULT"])
        
        contextual_info = f"""
        CURRENT CONTEXT:
        - User's Safety Status: {self.safety_status}
        - User's Location: {self.user_location or 'Not Provided'}
        - Available Helplines: {json.dumps(RESOURCES['helplines'])}
        - Available NGOs: {json.dumps(RESOURCES['ngos'])}
        - Available Legal Info: {json.dumps(RESOURCES['legal_info'])}
        """
        
        # Add specific instruction to prevent question repetition
        anti_repetition_rule = """
        CRITICAL: Do NOT repeat or translate the user's question. Answer directly without echoing their words.
        """
        
        full_system_prompt = f"{prompt_data['persona']}\n{contextual_info}\nRULES:\n{prompt_data['rules']}\n{anti_repetition_rule}"

        messages = [
            {"role": "system", "content": full_system_prompt},
            *self.chat_history[-6:],
            {"role": "user", "content": user_input}
        ]

        response_text = self._call_groq_api(messages)
        
        self.chat_history.extend([
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_text}
        ])
        
        return response_text

# --- Initialize the Assistant ---
try:
    groq_api_key = os.getenv("GROQ_API_KEY")
    if not groq_api_key:
        raise ValueError("GROQ_API_KEY not found in environment variables. Please set it in a .env file.")

    client = Groq(api_key=groq_api_key)
    client.models.list()
    print("Groq API key successfully validated.")

    # Create a global instance of the chatbot, passing the client to it
    assistant = SakhiChatbot(client=client)
    print("🌸 Sakhi - Your Safety Companion is ready. 🌸")

except (ValueError, AuthenticationError, APIConnectionError, APIError) as e:
    print(f"\nFatal Initialization Error: {e}")
    print("Sakhi cannot start. Please ensure your Groq API key is correctly set.")
    assistant = None
except Exception as e:
    print(f"\nCritical startup error: {type(e).__name__} - {e}")
    print("Sakhi cannot start due to an unforeseen issue.")
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
        return ChatResponse(reply="Please say something.")

    try:
        response = assistant.process_message(user_input)
        # FIX: Ensure proper UTF-8 encoding for Hindi text
        return ChatResponse(reply=response)
    except Exception as e:
        print(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred while processing your message.")

# --- Server Startup ---
if __name__ == "__main__":
    uvicorn.run(app, host='0.0.0.0', port=5000)
