import json
import logging
from pathlib import Path
from core.arabic_normalizer import normalize_arabic
from core.ai_engine import PediatricianAIAssistant

# إعداد الـ Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

class MessageRouter:
    def __init__(self):
        self.db_path = Path(__file__).resolve().parent.parent / "knowledge" / "router_db.json"
        self._load_db()
        self.ai_assistant = PediatricianAIAssistant() # استدعاء الـ AI كـ Fallback

    def _load_db(self):
        with open(self.db_path, 'r', encoding='utf-8') as f:
            self.db = json.load(f)

    def detect_intent(self, normalized_message: str) -> str:
        """Rule-based Intent Detection"""
        for intent_name, intent_data in self.db['intents'].items():
            for keyword in intent_data['keywords']:
                normalized_keyword = normalize_arabic(keyword)
                if normalized_keyword in normalized_message:
                    return intent_name
        return "unknown"

    def handle_user_message(self, user_id: str, message: str) -> dict:
        normalized_msg = normalize_arabic(message)
        intent = self.detect_intent(normalized_msg)
        
        buttons = self.db.get("buttons", [])

        # زر تجاوز الـ DB والذهاب للـ AI مباشرة
        if "اسأل المساعد" in message:
            intent = "unknown"

        if intent != "unknown":
            response_text = self.db['intents'][intent]['response']
            source = "DATABASE"
            ai_called = "NO"
        else:
            # Fallback to AI Engine
            response_text = self.ai_assistant.generate_reply(user_id, message)
            source = "AI_ENGINE"
            ai_called = "YES"

        # نظام Logging واضح
        logger.info(f"User: {message} | Intent: {intent} | Source: {source} | AI called: {ai_called}")

        return {
            "reply": response_text,
            "buttons": buttons,
            "source": source
        }