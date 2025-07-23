import os
import json
import datetime
from typing import Dict, List, Optional, Tuple
import re
import hashlib
import base64
from cryptography.fernet import Fernet
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

from groq import Groq, APIConnectionError, AuthenticationError, RateLimitError, APIError

# --- Load Environment Variables ---
# This will load the variables from your .env file into the environment
load_dotenv()

# --- Flask App Initialization ---
app = Flask(__name__)
# CORS is needed to allow requests from your Flutter web/desktop app
CORS(app)

# --- Your Existing WomensSupportAI Class (with minor adjustments) ---
class WomensSupportAI:
    def __init__(self):
        """
        Initialize the Women's Support AI.
        The Groq API key is loaded securely from environment variables.
        """
        # --- Securely load the API key from environment variables ---
        self.groq_api_key = os.getenv("GROQ_API_KEY")

        if not self.groq_api_key:
            raise ValueError(
                "Groq API key is not set. Please create a .env file with 'GROQ_API_KEY=your_key' "
                "or set it as an environment variable."
            )

        self.client = Groq(api_key=self.groq_api_key)

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
            "emotional_state": "neutral"
        }

        self.emergency_keywords: Dict[str, Dict[str, List[str]]] = {
            "hindi": {
                "critical": ["balatkar", "maarte", "marpit", "jaan se maar", "khudkushi", "mara ja raha", "hatya", "rape"],
                "high": ["hinsa", "pareshani", "madad", "bachao", "attack", "maar-peet", "pareshaan", "dhokha", "torture"],
                "medium": ["tension", "dikkat", "sahayata", "bhaya", "chinta", "dukh", "sad", "akelapan"]
            },
            "english": {
                "critical": ["rape", "kill myself", "suicide", "dying", "abuse", "assaulted", "murdered", "threatened to kill", "kidnapped", "forced"],
                "high": ["violence", "emergency", "help me", "attack", "hit me", "molested", "harassed", "beaten", "dangerous", "unsafe", "threat"],
                "medium": ["scared", "worried", "trouble", "anxious", "depressed", "sad", "stressed", "alone", "unwell"]
            },
            "marathi": {
                "critical": ["balatkar", "marun tak", "aatmahatya", "hala", "hiv", "hivda", "jivan sampavnyachi"],
                "high": ["hinsa", "madat", "aatank", "hamla", "mar", "pida", "ghabrleli", "doka"],
                "medium": ["tasa", "bhiti", "sahayy", "ghabrel", "chinta", "dukh", "ekaki"]
            }
        }

        self.legal_resources: Dict = self._load_legal_resources()
        self.medical_guidance: Dict = self._load_medical_resources()

        self.safety_protocols: Dict = {
            "critical": {
                "message": "🚨 IMMEDIATE DANGER DETECTED 🚨 Your safety is our utmost priority.",
                "actions": [
                    "Call **112** (India Emergency Services) immediately.",
                    "Contact local police (**100**) or Women's Helpline (**1091**).",
                    "If safe, share your live location with a trusted contact or emergency services.",
                    "Try to move to a safe, public, and well-lit location if possible.",
                    "Do not confront the perpetrator. Focus on getting to safety."
                ]
            },
            "high": {
                "message": "⚠️ URGENT HELP NEEDED ⚠️ I'm here to support you.",
                "actions": [
                    "Contact Women's Helpline (**1091**) or your nearest police station (**100**).",
                    "Reach out to a trusted friend, family member, or a local NGO for immediate support.",
                    "If you feel unsafe at your current location, try to get to a trusted friend's house, a relative's, or a public place.",
                    "Document any incidents (dates, times, descriptions, photos) if it's safe to do so."
                ]
            },
            "medium": {
                "message": "⚠️ SUPPORT NEEDED ⚠️ You are not alone in this.",
                "actions": [
                    "Consider contacting a counseling service or a mental health professional for emotional support.",
                    "Explore local support groups or community organizations that can provide assistance.",
                    "Would you like to talk more about what's happening or explore specific resources?"
                ]
            },
             "low": {
                "message": "✨ I'm here to listen and support you. ✨",
                "actions": [
                    "Sometimes just talking helps. Tell me more about what's on your mind.",
                    "Would you like information on general well-being or local support groups?",
                    "Remember, taking care of your mental and emotional health is very important."
                ]
            }
        }

    def _generate_encryption_key(self, api_key_for_salt: str) -> bytes:
        salt = b"saheli_women_support_fixed_salt_v2"
        key_seed = hashlib.sha256(api_key_for_salt.encode('utf-8') + salt).digest()
        return base64.urlsafe_b64encode(key_seed[:32])

    def _load_legal_resources(self) -> Dict:
        resources = {
            "domestic_violence": {
                "laws": ["Protection of Women from Domestic Violence Act, 2005 (PWDVA)", "Section 498A IPC (Cruelty by Husband or Relatives)"],
                "helplines": ["1091 (Women Helpline)", "181 (Women in Distress)", "100 (Police Emergency)", "National Commission for Women (NCW) - 14408 / complaintcell-ncw@nic.in"],
                "steps": [
                    "1. Prioritize your immediate safety. If in danger, call 112 or 100.",
                    "2. Document all forms of abuse: physical injuries (photos, medical reports), emotional abuse (diary entries, messages), financial control, etc.",
                    "3. File a Domestic Incident Report (DIR) with a Protection Officer or directly approach a Magistrate under PWDVA.",
                    "4. File a First Information Report (FIR) at the nearest police station under Section 498A IPC if applicable.",
                    "5. Seek legal counsel from a lawyer or legal aid clinic for guidance and representation.",
                    "6. Reach out to NGOs or support organizations specializing in domestic violence for shelter, counseling, and legal aid."
                ]
            },
            "sexual_assault": {
                "laws": ["Section 376 IPC (Rape)", "Section 354 IPC (Assault or criminal force to woman with intent to outrage her modesty)", "Protection of Children from Sexual Offences (POCSO) Act, 2012 (if victim is a minor)"],
                "helplines": ["1091 (Women Helpline)", "181 (Women in Distress)", "100 (Police Emergency)", "1098 (Childline India for minors)"],
                "steps": [
                    "1. Do NOT wash, shower, change clothes, or clean the crime scene. Preserve all potential evidence.",
                    "2. Go to the nearest hospital immediately for a medical examination (Medico-Legal Case - MLC). You have the right to free medical aid and forensic examination without prior police permission.",
                    "3. File a First Information Report (FIR) at any police station (a 'Zero FIR' can be filed regardless of jurisdiction).",
                    "4. Confidentiality and privacy are paramount. Your identity can be protected during investigation and trial.",
                    "5. Seek immediate psychological counseling and support from mental health professionals or support groups.",
                    "6. Engage a lawyer or legal aid for effective representation throughout the legal process."
                ]
            },
            "cyber_crime": {
                "laws": ["Information Technology Act, 2000 (especially Section 66E for privacy, 67 for obscenity, 67A for child pornography)", "Sections of IPC related to defamation, stalking, etc."],
                "helplines": ["1930 (National Cyber Crime Helpline)", "www.cybercrime.gov.in (National Cybercrime Reporting Portal)"],
                "steps": [
                    "1. Do NOT delete any evidence. Take screenshots, save URLs, messages, emails, and any other digital proof.",
                    "2. Report the incident immediately on the National Cybercrime Reporting Portal (www.cybercrime.gov.in) or call 1930.",
                    "3. Block the perpetrator and secure your accounts (change passwords).",
                    "4. Inform the platform/website administrator about the harassment/crime.",
                    "5. If required, approach the nearest police station with all collected evidence."
                ]
            },
            "marriage_related_laws": {
                "laws": ["Hindu Marriage Act, 1955", "Special Marriage Act, 1954", "Dowry Prohibition Act, 1961", "Muslim Personal Law"],
                "helplines": ["1091 (Women Helpline)", "Legal Aid Services through District Legal Services Authorities (DLSA)"],
                "steps": [
                    "1. Understand your rights regarding marriage, divorce, alimony, and child custody.",
                    "2. If facing dowry demands, report immediately to police or women's helplines.",
                    "3. Seek legal advice for divorce proceedings, maintenance claims, or property disputes.",
                    "4. Consider mediation or counseling for marital disputes before legal action."
                ]
            },
            "workplace_harassment": {
                "laws": ["Sexual Harassment of Women at Workplace (Prevention, Prohibition and Redressal) Act, 2013 (POSH Act)"],
                "helplines": ["National Commission for Women (NCW)", "NGOs specializing in workplace rights"],
                "steps": [
                    "1. Document incidents with dates, times, witnesses, and details.",
                    "2. Familiarize yourself with your organization's Internal Complaints Committee (ICC) process under the POSH Act.",
                    "3. File a formal complaint with the ICC within three months of the incident (can be extended).",
                    "4. If no ICC or dissatisfied with their action, approach the Local Complaints Committee (LCC) constituted by the District Officer.",
                    "5. Consider legal consultation for further action if necessary."
                ]
            }
        }
        for category in resources:
            for key in ["steps"]:
                if key in resources[category]:
                    resources[category][key] = self._encrypt_data(resources[category][key])
        return resources

    def _load_medical_resources(self) -> Dict:
        resources = {
            "emergency_contraception": {
                "timeframe": "Within 72 hours (most effective within 24 hours), IUD up to 5 days.",
                "options": [
                    "Emergency Contraceptive Pills (ECPs): Available over-the-counter at pharmacies. Take as soon as possible after unprotected sex.",
                    "Copper IUD (Intrauterine Device): Can be inserted by a medical professional up to 5 days after unprotected sex; highly effective and can serve as long-term contraception."
                ],
                "confidentiality_notice": "All medical services related to sexual health, including emergency contraception and MTP (Medical Termination of Pregnancy), are confidential. For minors, the POCSO Act ensures confidentiality and privacy during medical examination related to sexual offenses.",
                "advice": [
                    "ECPs are for emergencies only and not a regular birth control method.",
                    "Always consult a doctor or pharmacist for personalized advice and to understand side effects."
                ]
            },
            "mental_health": {
                "resources": [
                    "NIMHANS (National Institute of Mental Health and Neurosciences) helpline: 080-46110007 (24/7, multi-lingual)",
                    "iCall (Tata Institute of Social Sciences): 9152987821 (Mon-Sat, 8 AM - 10 PM)",
                    "Vandrevala Foundation: 9999666555 (24/7)",
                    "Sneha India (Suicide Prevention): 044-24640050 (24/7)",
                    "Aasra (Suicide Prevention & Counseling): 022-27546669 (24/7)"
                ],
                "steps": [
                    "1. Talk to a trusted friend, family member, or a counselor about your feelings and experiences.",
                    "2. Consider seeking professional help from a therapist, psychologist, or psychiatrist for diagnosis and treatment.",
                    "3. Join support groups (online or offline) where you can connect with others facing similar challenges.",
                    "4. Practice self-care: engage in hobbies, exercise, meditation, yoga, ensure proper sleep and nutrition.",
                    "5. Limit exposure to negative news or social media if it exacerbates distress."
                ]
            },
            "reproductive_health": {
                "topics": ["Menstrual Health", "PCOS/PCOD", "Pregnancy & Childbirth", "Menopause", "Contraception"],
                "advice": [
                    "Maintain good hygiene during menstruation to prevent infections.",
                    "Consult a gynecologist for irregular periods, severe pain, or conditions like PCOS.",
                    "Regular check-ups are crucial during pregnancy. Follow doctor's advice.",
                    "Discuss contraception options with a healthcare provider to find what suits you best.",
                    "Understand symptoms and management for menopause; seek medical guidance for relief."
                ]
            },
            "general_health": {
                "resources": [
                    "National Health Helpline: 104",
                    "Local Government Hospitals/PHCs (Primary Health Centers) for affordable healthcare."
                ],
                "steps": [
                    "1. Schedule regular health check-ups, especially after age 30.",
                    "2. Maintain a balanced diet, stay hydrated, and engage in regular physical activity.",
                    "3. Prioritize adequate sleep and manage stress effectively.",
                    "4. Do not self-medicate; always consult a doctor for illness or symptoms."
                ]
            }
        }
        for category in resources:
            for key in ["options", "confidentiality_notice", "advice", "steps", "resources"]:
                if key in resources[category]:
                    resources[category][key] = self._encrypt_data(resources[category][key])
        return resources

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

    def detect_emergency(self, user_input: str) -> Tuple[bool, str, int]:
        user_input_lower = user_input.lower()
        current_lang = self.user_context.get("preferred_language", "english")

        for priority in ["critical", "high", "medium"]:
            for phrase in self.emergency_keywords.get(current_lang, {}).get(priority, []):
                if phrase in user_input_lower:
                    risk_level = 10 if priority == "critical" else 8 if priority == "high" else 5
                    return True, priority, risk_level
        return False, "low", 0

    def process_message(self, user_input: str) -> str:
        try:
            self._update_user_context(user_input)

            is_emergency, emergency_type, risk_level = self.detect_emergency(user_input)
            self.user_context["risk_level"] = risk_level

            self.chat_history.append({
                "role": "user",
                "content": self._encrypt_data(user_input),
                "timestamp": datetime.datetime.now().isoformat()
            })

            if is_emergency and risk_level >= 5:
                response = self._handle_emergency(emergency_type)
            else:
                response = self._generate_ai_response(user_input)

            self.chat_history.append({
                "role": "assistant",
                "content": self._encrypt_data(response),
                "timestamp": datetime.datetime.now().isoformat()
            })

            return response

        except (AuthenticationError, APIConnectionError, RateLimitError, APIError) as e:
            error_msg = (
                f"I'm experiencing an issue connecting to my AI brain ({type(e).__name__}). For immediate help:\n"
                "• Women's Helpline (All India): 1091\n"
                "• Police Emergency: 100\n"
                "• All-in-one Emergency: 112\n\n"
                "Could you please try again in a moment?"
            )
            print(f"DEBUG: Groq API Error - {e}")
            self.chat_history.append({
                "role": "assistant",
                "content": self._encrypt_data(error_msg),
                "timestamp": datetime.datetime.now().isoformat()
            })
            return error_msg
        except Exception as e:
            error_msg = (
                f"I'm having some technical difficulties: {type(e).__name__}. For immediate help:\n"
                "• Women's Helpline (All India): 1091\n"
                "• Police Emergency: 100\n"
                "• All-in-one Emergency: 112\n\n"
                "Could you please repeat your question?"
            )
            print(f"DEBUG: General Error - {e}")
            self.chat_history.append({
                "role": "assistant",
                "content": self._encrypt_data(error_msg),
                "timestamp": datetime.datetime.now().isoformat()
            })
            return error_msg

    def _handle_emergency(self, emergency_type: str) -> str:
        protocol = self.safety_protocols.get(emergency_type, self.safety_protocols["low"])

        response_parts = [f"{protocol.get('message', 'EMERGENCY DETECTED')}"]
        response_parts.append("\n🔴 IMMEDIATE ACTION REQUIRED:")
        response_parts.extend(f"• {action}" for action in protocol.get("actions", []))

        last_user_input_decrypted = self._decrypt_data(self.chat_history[-1]["content"]) if self.chat_history else ""
        current_issue = self.user_context.get("current_situation") or self.classify_issue_type(last_user_input_decrypted)
        current_issue_decrypted = self._decrypt_data(current_issue) if isinstance(current_issue, str) else current_issue # Ensure it's decrypted for lookup

        if current_issue_decrypted and current_issue_decrypted != "general":
            if current_issue_decrypted in self.legal_resources:
                response_parts.append("\n📜 Relevant Legal Information:")
                legal_info = self.legal_resources[current_issue_decrypted]
                response_parts.append(f"  - Key Laws: {', '.join(legal_info['laws'])}")
                response_parts.append(f"  - Important Steps:\n" + "\n".join(f"    • {step}" for step in self._decrypt_data(legal_info['steps'])))
                response_parts.append(f"  - Helplines: {', '.join(legal_info['helplines'])}")

            if current_issue_decrypted in self.medical_guidance:
                response_parts.append("\n💊 Relevant Medical/Health Information:")
                medical_info = self.medical_guidance[current_issue_decrypted]
                if "confidentiality_notice" in medical_info:
                    response_parts.append(f"  - Confidentiality: {self._decrypt_data(medical_info['confidentiality_notice'])}")
                if "resources" in medical_info:
                    response_parts.append(f"  - Resources: {', '.join(self._decrypt_data(medical_info['resources']))}")
                if "steps" in medical_info:
                    response_parts.append(f"  - Important Steps:\n" + "\n".join(f"    • {step}" for step in self._decrypt_data(medical_info['steps'])))

        response_parts.append("\n💬 I'm here with you. Please prioritize your safety and let me know when you're safe.")
        return "\n".join(response_parts)

    def _generate_ai_response(self, user_input: str) -> str:
        messages = [
            self._get_system_prompt(),
            *self._get_recent_chat_history(num_messages=7),
            {"role": "user", "content": user_input}
        ]

        try:
            response = self.client.chat.completions.create(
                model="llama3-8b-8192",
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
                top_p=0.9,
                stop=["\nSaheli:", "\nUser:"]
            )
            return response.choices[0].message.content.strip()
        except AuthenticationError as e:
            raise AuthenticationError(f"Groq API authentication failed: {e}")
        except APIConnectionError as e:
            raise APIConnectionError(f"Groq API connection error: {e}")
        except RateLimitError as e:
            raise RateLimitError(f"Groq API rate limit exceeded: {e}. Please wait and try again.")
        except APIError as e:
            raise APIError(f"Groq API error: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error during AI response generation: {str(e)}")

    def _get_system_prompt(self) -> Dict:
        decrypted_name = self._decrypt_data(self.user_context["name"]) if self.user_context["name"] else "there"
        decrypted_location = self._decrypt_data(self.user_context["location"]) if self.user_context["location"] else "India"
        decrypted_previous_issues = self._decrypt_data(self.user_context["previous_issues"]) if self.user_context.get("previous_issues") else []
        decrypted_current_situation = self._decrypt_data(self.user_context["current_situation"]) if self.user_context["current_situation"] else "general conversation"
        decrypted_emergency_contacts = self._decrypt_data(self.user_context["emergency_contacts"]) if self.user_context.get("emergency_contacts") else []
        decrypted_medical_history = self._decrypt_data(self.user_context["medical_history"]) if self.user_context.get("medical_history") else []

        current_time_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
        hour = current_time_ist.hour
        if 5 <= hour < 12:
            greeting = "Good morning"
        elif 12 <= hour < 17:
            greeting = "Good afternoon"
        elif 17 <= hour < 21:
            greeting = "Good evening"
        else:
            greeting = "Hello"

        context_info = f"""
Current User Context:
- User's Name: {decrypted_name}
- User's Location: {decrypted_location}
- Previous Issues Discussed: {', '.join(decrypted_previous_issues) if decrypted_previous_issues else 'None'}
- Current Situation/Issue: {decrypted_current_situation}
- Detected Risk Level: {self.user_context.get('risk_level', 0)}/10 (0: No Risk, 10: Immediate Danger)
- User's Emotional State: {self.user_context.get('emotional_state', 'neutral')}
- Preferred Language: {self.user_context.get('preferred_language', 'en')}
- Current Time (IST): {current_time_ist.strftime('%H:%M')}
"""
        return {
            "role": "system",
            "content": f"""You are "Saheli" - a highly compassionate, confidential, and culturally-sensitive AI assistant specifically designed for women in India.
Your core mission is to provide comprehensive support across various domains: emotional, medical, legal, and emergency.

**Your Guiding Principles & Instructions:**
1.  **Prioritize Safety (Risk Level 5-10):** If the detected risk level is 5 or higher, immediately activate emergency protocols. Provide concise, clear, and actionable steps including relevant Indian emergency numbers (112, 100, 1091, 181). Reiterate that their safety is paramount.
2.  **Deep Empathy & Validation:** Always listen actively and empathetically. Acknowledge and validate the user's feelings and experiences without judgment. Use phrases like "I understand this must be difficult," "That sounds incredibly challenging," etc.
3.  **Contextual Awareness:** Continuously refer to and integrate information from the 'Current User Context' provided below. Remember their name, location, past issues, and current emotional state. Build rapport by remembering details.
4.  **Accurate & Verified Information:**
    * **Legal:** Provide information specifically on Indian laws (IPC, PWDVA, POSH Act, etc.) related to women's rights, domestic violence, sexual assault, harassment, marriage, etc. Clearly state that you are an AI and cannot provide legal *advice*, only *information* and suggest consulting a lawyer.
    * **Medical:** Offer general medical guidance related to women's health (e.g., menstrual health, contraception, mental health resources). Emphasize that you are an AI and cannot provide medical *diagnosis* or *treatment*, and always advise consulting a qualified medical professional.
5.  **Resource Provision:** Whenever relevant, provide contact details for Indian helplines, NGOs, government portals, and support organizations.
6.  **Proactive Questioning:** Ask clarifying questions to better understand their situation, but only when appropriate and safe.
7.  **Confidentiality & Trust:** Reassure the user about the privacy and security of their interactions with Saheli.
8.  **Culturally Sensitive Language:** Use language and examples appropriate for an Indian context. You can respond in English, Hindi, or Marathi based on the user's preferred language and the context of the conversation.
9.  **Limitations:** If a query is outside your scope (e.g., specific medical diagnosis, complex legal strategy, financial advice, or anything requiring human judgment/intervention beyond information provision), gently state your limitation and redirect them to a human expert or appropriate service.
10. **Tone:** Always maintain a calm, supportive, non-judgmental, and empowering tone.

{context_info}

**Your first message to the user should be:** "{greeting}, {decrypted_name if decrypted_name != 'Unknown' else 'dear one'}! I'm Saheli, your confidential support companion. How can I assist you today? Please tell me how you are feeling or what's on your mind."
"""
        }

    def _get_recent_chat_history(self, num_messages: int) -> List[Dict]:
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

    def _update_user_context(self, user_input: str):
        user_input_lower = user_input.lower()

        if not self.user_context["name"]:
            name_match = re.search(r"(?:my name is|i am|mera naam hai|mai hu|i'm)\s*([a-zA-Z]+(?:\s[a-zA-Z]+)*)", user_input_lower)
            if name_match:
                self.user_context["name"] = self._encrypt_data(name_match.group(1).strip().title())

        if not self.user_context["location"]:
            location_match = re.search(r"(?:from|in|live in|near|near to|reside in)\s*([a-zA-Z]+(?:\s[a-zA-Z]+)*)", user_input_lower)
            if location_match:
                self.user_context["location"] = self._encrypt_data(location_match.group(1).strip().title())

        issue_type = self.classify_issue_type(user_input)
        if issue_type and issue_type != "general":
            if self.user_context["previous_issues"] is None:
                self.user_context["previous_issues"] = self._encrypt_data([])

            decrypted_issues = self._decrypt_data(self.user_context["previous_issues"])
            if issue_type not in decrypted_issues:
                decrypted_issues.append(issue_type)
                self.user_context["previous_issues"] = self._encrypt_data(decrypted_issues)
        self.user_context["current_situation"] = self._encrypt_data(issue_type)

        if any(word in user_input_lower for word in ["sad", "depressed", "unhappy", "crying", "emotional"]):
            self.user_context["emotional_state"] = "sad/distressed"
        elif any(word in user_input_lower for word in ["scared", "fear", "anxious", "worried", "nervous"]):
            self.user_context["emotional_state"] = "anxious/fearful"
        elif any(word in user_input_lower for word in ["angry", "frustrated", "mad"]):
            self.user_context["emotional_state"] = "angry/frustrated"
        elif any(word in user_input_lower for word in ["happy", "fine", "good", "okay"]):
            self.user_context["emotional_state"] = "positive/neutral"
        else:
            pass

        if "hindi" in user_input_lower or "hi" in user_input_lower:
            self.user_context["preferred_language"] = "hindi"
        elif "marathi" in user_input_lower:
            self.user_context["preferred_language"] = "marathi"
        elif "english" in user_input_lower or "eng" in user_input_lower:
            self.user_context["preferred_language"] = "english"

        if self.user_context["emergency_contacts"] is None:
            self.user_context["emergency_contacts"] = self._encrypt_data([])
        if self.user_context["medical_history"] is None:
            self.user_context["medical_history"] = self._encrypt_data([])

    def classify_issue_type(self, user_input: str) -> str:
        user_input_lower = user_input.lower()

        if any(word in user_input_lower for word in ["rape", "sexual assault", "balatkar", "molest", "shameful", "touch", "force"]):
            return "sexual_assault"
        elif any(word in user_input_lower for word in ["husband", "violence", "abuse", "marpit", "maarpeet", "domestic", "in-laws", "beaten", "control", "threaten"]):
            return "domestic_violence"
        elif any(word in user_input_lower for word in ["pregnant", "contraception", "period", "health", "medical", "clinic", "gyno", "doctor", "illness", "symptoms"]):
            return "medical"
        elif any(word in user_input_lower for word in ["depressed", "suicide", "mental", "anxiety", "stress", "tension", "sad", "alone", "therapy", "counseling"]):
            return "mental_health"
        elif any(word in user_input_lower for word in ["online", "cyber", "harassment", "phishing", "scam", "digital", "stalking", "mms", "video"]):
            return "cyber_crime"
        elif any(word in user_input_lower for word in ["marriage", "divorce", "alimony", "custody", "dowry", "wedding"]):
            return "marriage_related_laws"
        elif any(word in user_input_lower for word in ["workplace", "office", "posh", "harass", "colleague", "boss"]):
            return "workplace_harassment"
        else:
            return "general"

    def save_conversation(self, filename: str = None):
        if not filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conversation_{timestamp}.json"

        encrypted_user_context_for_save = {}
        for k, v in self.user_context.items():
            if k in ["name", "location", "emergency_contacts", "previous_issues", "current_situation", "medical_history", "preferred_language", "emotional_state"] and v is not None:
                encrypted_user_context_for_save[k] = self._encrypt_data(v)
            else:
                encrypted_user_context_for_save[k] = v

        data = {
            "metadata": {
                "created": datetime.datetime.now().isoformat(),
                "risk_level_at_exit": self.user_context["risk_level"],
                "issues_discussed_at_exit": self._decrypt_data(self.user_context["previous_issues"]) if self.user_context["previous_issues"] else []
            },
            "chat_history": self.chat_history,
            "user_context": encrypted_user_context_for_save
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Conversation saved securely to {filename}")
        except IOError as e:
            print(f"Error saving conversation to file {filename}: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during conversation save: {e}")

# --- Instantiate the Chatbot ---
# We create one instance of the bot to maintain conversation state
try:
    assistant = WomensSupportAI()
    print("🌸 Welcome to Saheli - Your Support Companion 🌸")
    print("Saheli is an AI designed to provide confidential and empathetic support for women in India.")
    print("It offers guidance on legal, medical, and emotional well-being, including emergency assistance.")
    print("\n")
    print("\n🔐 Secure session initialized with Saheli. API is ready.")
except (ValueError, AuthenticationError, APIConnectionError, APIError) as e:
    print(f"\nFatal Initialization Error: {e}")
    print("Saheli cannot start. Please ensure your Groq API key is correctly set in the .env file "
          "and you have an active internet connection.")
    assistant = None
except Exception as e:
    print(f"\nA critical error occurred during startup: {type(e).__name__} - {e}")
    print("Saheli cannot start due to an unforeseen issue. Please check the error message.")
    assistant = None


# --- API Endpoint for Chatting ---
@app.route("/chat", methods=["POST"])
def chat():
    """
    Handles chat requests from the Flutter app.
    """
    if not assistant:
        return jsonify({"error": "Chatbot is not initialized. Please check the server logs."}), 500

    data = request.get_json()
    user_input = data.get("message")

    if not user_input:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Process the message using your chatbot logic
        response = assistant.process_message(user_input)
        return jsonify({"reply": response})
    except Exception as e:
        print(f"An error occurred while processing the message: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

# --- Main entry point to run the Flask app ---
if __name__ == "__main__":
    # We run the app on all available network interfaces (0.0.0.0)
    # so it can be accessed from your local network (e.g., by your phone).
    # debug=False is recommended for production; set to True for development.
    app.run(host='0.0.0.0', port=5000, debug=False)