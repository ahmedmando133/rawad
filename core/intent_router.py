"""
Deterministic Intent Router (Zero-Token Fast Responder).

Routes routine administrative inquiries directly to local database answers,
bypassing the LLM completely to eliminate token cost, eliminate latency, and
guarantee 100% factual accuracy for clinic facts.

Inquiries about child health or symptoms are intentionally NOT intercepted
here and are passed to the Gemini conversational engine.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from core.database import AssistantDatabase
from core.safety_filter import normalize_arabic

logger = logging.getLogger(__name__)

# Routine Intent Patterns (Normalized Arabic)
_LOCATION_PATTERNS = [
    r"\b(?:وين|فين|اين)\s*(?:مكان|مقر|موقع)?\s*(?:العياده|العيادة|الدكتور|المجمع)\b",
    r"\b(?:مكان|مقر|موقع|عنوان)\s*(?:العياده|العيادة|الدكتور|المجمع)\b",
    r"\bوينكم\b|\bوين\s*تجو\b|\bوين\s*قاعدين\b|\bمكانكم\s*وين\b",
]

_HOURS_PATTERNS = [
    r"\b(?:امتى|متى|شنو|شن)\s*(?:تفتحوا|تسكرو|اوقات|مواعيد|ساعات|دوام)\b",
    r"\b(?:اوقات|مواعيد|ساعات|ايام)\s*(?:الدوام|العمل|العياده|الدكتور|الكشف)\b",
    r"\bمفتوحين\s*(?:اليوم|توا|غدوه|غدوة)?\b",
    r"\bامتى\s*(?:يداوم|يجي|يكون\s*موجود)\s*الدكتور\b",
]

_PHONE_PATTERNS = [
    r"\b(?:رقم|هاتف|تليفون|موبايل|واتساب|واتس)\s*(?:العياده|العيادة|الحجز|الدكتور|الاتصال)?\b",
    r"\b(?:كيف|كيفاش)\s*(?:نحجز|نتصل|نتواصل)\b",
    r"\bنبي\s*رقم\b|\bاعطيني\s*الرقم\b|\bعندكم\s*واتساب\b",
]

_FEES_PATTERNS = [
    r"\b(?:بكم|بقداش|قداش|كم|سعر|تكلفه|تكلفة|ثمن)\s*(?:الكشف|كشف|المعاينة|معاينه|الدخوليه)?\b",
    r"\bالكشف\s*(?:بكم|بقداش|قداش)\b",
]

_DOCTOR_PATTERNS = [
    r"\b(?:من|شن\s*اسم|اسم)\s*الدكتور\b",
    r"\bشنو\s*تخصص\s*الدكتور\b",
]

_COMPILED_INTENTS = {
    "location": [re.compile(p) for p in _LOCATION_PATTERNS],
    "hours": [re.compile(p) for p in _HOURS_PATTERNS],
    "phone": [re.compile(p) for p in _PHONE_PATTERNS],
    "fees": [re.compile(p) for p in _FEES_PATTERNS],
    "doctor": [re.compile(p) for p in _DOCTOR_PATTERNS],
}

# Words indicating a clinical symptom or question that must go to the AI
_CLINICAL_SYMPTOM_WORDS = {
    "سخان", "سخانه", "حراره", "كحه", "يكح", "يرجع", "استفراغ",
    "اسهال", "بطنه", "وجع", "يوجع", "مريض", "تعبان", "طفح", "حبوب",
    "عمره", "سنتين", "شهور", "صغير", "ولدي", "بنتي", "طفلي", "رضيع",
    "دوا", "دواء", "مضاد", "جرعه", "جرعة"
}


@dataclass
class IntentRouteResult:
    matched: bool
    intent: str | None
    direct_reply: str | None
    tokens_consumed: int = 0


class IntentRouter:
    """Routes messages to direct DB answers or allows pass-through to LLM."""

    def __init__(self, db: AssistantDatabase) -> None:
        self.db = db

    def route(self, user_message: str) -> IntentRouteResult:
        normalized = normalize_arabic(user_message)
        words = set(normalized.split())

        # If user is describing a child's clinical case, pass to AI
        # (even if they also asked about an appointment)
        if any(w in words for w in _CLINICAL_SYMPTOM_WORDS):
            return IntentRouteResult(matched=False, intent="clinical_inquiry", direct_reply=None)

        # 1. Check direct FAQ matcher from Database
        faq_match = self.db.find_direct_faq(user_message)
        if faq_match:
            logger.info("Direct FAQ matched in DB for query: %s", user_message[:30])
            return IntentRouteResult(
                matched=True,
                intent="faq_direct",
                direct_reply=faq_match,
                tokens_consumed=0,
            )

        # 2. Check administrative regex intents
        for intent_name, patterns in _COMPILED_INTENTS.items():
            if any(p.search(normalized) for p in patterns):
                reply = self._get_intent_reply(intent_name)
                if reply:
                    logger.info("Intent matched [%s] for query: %s", intent_name, user_message[:30])
                    return IntentRouteResult(
                        matched=True,
                        intent=intent_name,
                        direct_reply=reply,
                        tokens_consumed=0,
                    )

        # No direct admin intent matched -> Pass to Gemini
        return IntentRouteResult(matched=False, intent=None, direct_reply=None)

    def _get_intent_reply(self, intent: str) -> str | None:
        if intent == "location":
            return (
                "عيادة الدكتور رواد شحيمة في مجمع عيادات الرباط، "
                "تاجوراء - الطريق الوسطى، بالقرب من المجلس البلدي تاجوراء 📍"
            )
        if intent == "hours":
            return (
                "مواعيد د. رواد شحيمة في مجمع عيادات الرباط:\n"
                "• السبت: الفترة المسائية\n"
                "• الثلاثاء: طوال اليوم (24 ساعة)\n"
                "• الخميس: طوال اليوم (24 ساعة) 🌷"
            )
        if intent == "phone":
            return (
                "تقدر تحجز وتستفسر بالاتصال أو المراسلة عبر الواتساب "
                "على الرقم: 0914107262 🙏"
            )
        if intent == "fees":
            return (
                "سعر الكشف غير معلن في الصفحة، تقدر تتواصل مباشرة مع العيادة "
                "للاستفسار على الرقم: 0914107262 🌷"
            )
        if intent == "doctor":
            return (
                "الدكتور رواد شحيمة، طبيب أطفال ورعاية حديثي الولادة "
                "بمجمع عيادات الرباط بتاجوراء 🌷"
            )
        return None
