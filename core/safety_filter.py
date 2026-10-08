"""
Deterministic, pre-LLM emergency red-flag filter.

Why this exists:
    Emergency routing must NOT depend on the LLM being available or behaving
    correctly. This module runs BEFORE any Gemini call. If a red flag is
    detected, the engine returns the approved emergency reply immediately and
    never calls the API.

Design principles:
    - Bias toward safety: a false positive (unnecessary ER advice) is far less
      harmful than a false negative (missed emergency). Negations such as
      "ما عندهش تشنجات" are intentionally NOT filtered out.
    - Pure Python, no I/O at match time, no network. Fast and testable.
    - Categories mirror knowledge/safety_guardrails.md §2 (and §8 for ingestion).

All patterns are written against NORMALIZED text (see `normalize_arabic`):
    أ/إ/آ → ا, ى → ي, ة → ه, ؤ → و, ئ → ي, diacritics & tatweel removed,
    Arabic-Indic digits → ASCII digits, lowercase.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Normalization
# --------------------------------------------------------------------------- #
_DIACRITICS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_CHAR_MAP = str.maketrans(
    {
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ئ": "ي", "ؤ": "و", "ة": "ه",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
        "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
        "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
        "٫": ".", "،": " ", "؟": " ",
    }
)


def normalize_arabic(text: str) -> str:
    text = _DIACRITICS_RE.sub("", text or "")
    text = text.translate(_CHAR_MAP).lower()
    # Collapse elongated letters typed for emphasis: "هلبااااا" → "هلبا"
    text = re.sub(r"(.)\1{2,}", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------- #
# Red-flag patterns (normalized-text regexes)
# --------------------------------------------------------------------------- #
_NEG = r"(?:مش|ما|مو|موش|مهو|مهوش)"           # Libyan negators
_ABLE = r"(?:قادر|قادره|يقدر|تقدر|يقدرش|تقدرش)"
_FACE = r"(?:شفايف|شفته|شفتيه|وجه|لون|جلد|اظافر|صوابع|ايدي|رجلي|لسان)\S*"

RED_FLAG_PATTERNS: dict[str, list[str]] = {
    # 1. Severe difficulty breathing
    "breathing_difficulty": [
        rf"{_NEG}\s*{_ABLE}\s*(?:ي|ت)?تنفس",
        rf"{_NEG}\s*(?:ي|ت)تنفس",
        r"(?:ضيق|صعوبه|كتمه)\s*(?:في\s*)?(?:ال)?(?:نفس|تنفس)",
        r"نفس(?:ه|ها)?\s*(?:يتقطع|تتقطع|مقطوع|واقف|وقف)",
        r"صدر(?:ه|ها)?\s*(?:يدخل|تدخل|يصفر|تصفر|يزيز|يطلع\s*ويهبط)",
        r"\b(?:يلهث|تلهث|يشهق|تشهق)\b",
        r"can'?t\s+breathe|cannot\s+breathe|not\s+breathing|difficulty\s+breathing|short(?:ness)?\s+of\s+breath",
    ],
    # 2. Cyanosis / alarming colour change
    "cyanosis": [
        r"\b(?:ازرق|زرق|زرقا|زرقاء|مزرق|ازرقت|زرقان|زرقه)\b",
        rf"{_FACE}\s*(?:\S+\s*){{0,3}}(?:ازرق|زرق|مزرق)",
        r"لون(?:ه|ها)?\s*(?:متغير|تغير|مخطوف|اتغير)|(?:تغير|اتغير)\s*لون(?:ه|ها)?",
        r"\bblue\s+(?:lips|face|skin)|turning\s+blue|cyanos",
    ],
    # 3. Seizures
    "seizures": [
        r"تشنج|يتشنج|تتشنج|\bصرع\b|نوبه\s*(?:صرع|تشنج)|جات(?:ه|ها)\s*نوبه",
        r"عيون(?:ه|ها)?\s*(?:طالعه|مقلوبه|مقلبه|فوق)",
        r"يرعش\s*و\s*(?:عيون|ما\s*ي)|ينتفض\s*و",
        r"seizure|convuls|having\s+a\s+fit|\bfitting\b",
    ],
    # 4. Loss of consciousness
    "loss_of_consciousness": [
        r"مغمي|مغمى|اغمي|اغمى|غمي\s*علي|فاقد\s*(?:ال)?وعي|فقد\s*(?:ال)?وعي",
        rf"{_NEG}\s*(?:فاق|يفيق|تفيق|فاقش|فاقتش|واعي|واعيه)\b",
        r"طاح\s*و\s*ما|طاحت\s*و\s*ما",
        r"unconscious|passed\s+out|fainted|unresponsive",
    ],
    # 5. Severe dehydration
    "severe_dehydration": [
        rf"{_NEG}\s*(?:بال|يبول|تبول|بالش|يبولش|بالتش)\b",
        r"(?:يبكي|تبكي)\s*(?:بلا|بدون|من\s*غير)\s*دموع",
        r"(?:فم|لسان)(?:ه|ها)?\s*ناشف",
        r"(?:يرجع|ترجع|يستفرغ|تستفرغ|يتقيا|تتقيا)\s*(?:في\s*)?كل\s*(?:شي|شيء|حاجه)",
        r"\bجفاف\b|dehydrat|no\s+(?:urine|tears)",
    ],
    # 6. Severe allergic reaction
    "severe_allergic_reaction": [
        r"(?:وجه|شفايف|شفت|عيون|لسان|رقبت|حلق)\S*\s*(?:\S+\s*){0,2}(?:انتفخ|منتفخ|منفخ|متنفخ|نافخ|ورم|وارم|تورم)",
        r"(?:انتفخ|تنفخ|نفخ|ورم|تورم)\S*\s*(?:وجه|شفايف|عيون|لسان|حلق)",
        r"حساسيه\s*(?:قويه|شديده)|صدمه\s*(?:تحسسيه|حساسيه)",
        r"anaphyla|swollen\s+(?:face|lips|tongue|throat)",
    ],
    # 7. Choking
    "choking": [
        r"يختنق|تختنق|مختنق|مختنقه|اختنق|خنق",
        r"\b(?:شرق|شرقت|يشرق|تشرق)\b\s*(?:ب|في|و|$)",
        r"(?:حاجه|حبه|شي|لعبه)\s*(?:\S+\s*){0,2}(?:وقفت|واقفه|حاصله|علقت)\s*في\s*(?:حلق|زرد)",
        r"chok",
    ],
    # 8. Severe bleeding
    "severe_bleeding": [
        r"نزيف|ينزف|تنزف",
        r"دم\s*(?:هلبا|واجد|ياسر)",
        rf"(?:ال)?دم\s*{_NEG}\s*(?:وقف|يوقف|وقفش|يوقفش)|{_NEG}\s*(?:وقف|يوقف)\S*\s*(?:ال)?دم",
        r"bleeding\s+(?:a\s+lot|heavily|won'?t\s+stop)|heavy\s+bleeding",
    ],
    # 9. Rapid deterioration
    "rapid_deterioration": [
        r"يتدهور|تتدهور|تدهور",
        r"(?:فجاه|فجأه|بسرعه)\s*(?:\S+\s*){0,2}(?:تعب|طاح|خاب|ساء)",
        r"getting\s+worse\s+(?:fast|quickly)|deteriorat",
    ],
    # 10. Severe lethargy
    "severe_lethargy": [
        r"\bمرخي\b|\bمرخيه\b|(?:خامل|خامله)\s*(?:هلبا|خالص|برشا)",
        rf"{_NEG}\s*(?:يتحرك|تتحرك|يتحركش|تتحركش|يتجاوب|تتجاوب|يتجاوبش|يرد|ترد|يردش|تردش)",
        r"صعب\s*(?:ن)?(?:صحي|نفيق|يصحى|يفيق)|{neg}\s*(?:يصحى|يصحاش|نقدر\s*نصحي)".replace("{neg}", _NEG),
        r"letharg|\blimp\b|won'?t\s+wake",
    ],
    # §8 Accidental ingestion of medication / chemicals (treated as emergency)
    "toxic_ingestion": [
        r"(?:شرب|شربت|بلع|بلعت|كلا|كلات|اكل)\s*(?:\S+\s*){0,2}(?:ال)?(?:كلوركس|كلور|جافيل|ديتول|بنزين|كاز|مبيد|سم|سموم|بطاريه|مغناطيس)\b",
        r"(?:شرب|شربت|بلع|بلعت|كلا|كلات)\s*(?:\S+\s*){0,2}(?:حبوب|دوا|ادويه)\S*\s*(?:\S+\s*){0,3}(?:بالغلط|غلط|هلبا|كامل|كلها|كله)",
        r"(?:علبه|شريط|باكو)\s*(?:\S+\s*){0,1}(?:حبوب|دوا)\S*\s*(?:\S+\s*){0,2}(?:كامل|كله|كلها)|بلع\s*(?:\S+\s*){0,1}(?:علبه|شريط)",
        r"swallowed\s+(?:pills|medicine|bleach|battery|poison)|poison",
    ],
    # User-requested threshold (NOT in the doctor-approved guardrail list yet;
    # pending doctor sign-off): fever reading of 40°C or higher.
    "high_fever_40": [
        r"(?:حراره|حرارت|سخانه|سخانت|سخونه|درجه|درجت|fever|temp)\S*\D{0,15}?\b(?:4[0-4])(?:\.\d+)?\b",
    ],
}

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    cat: [re.compile(p) for p in pats] for cat, pats in RED_FLAG_PATTERNS.items()
}


@dataclass(frozen=True)
class RedFlagResult:
    is_emergency: bool
    categories: tuple[str, ...]


def detect_red_flags(message: str) -> RedFlagResult:
    """Return the red-flag categories found in `message` (empty if none)."""
    text = normalize_arabic(message)
    hits = tuple(
        cat for cat, patterns in _COMPILED.items() if any(p.search(text) for p in patterns)
    )
    return RedFlagResult(is_emergency=bool(hits), categories=hits)


# --------------------------------------------------------------------------- #
# Emergency reply (sourced from knowledge/safety_guardrails.md)
# --------------------------------------------------------------------------- #
# Used only if the template cannot be parsed from the guardrails file.
# Must stay identical to the "Template (Libyan Arabic)" in safety_guardrails.md.
DEFAULT_EMERGENCY_REPLY = "هذي حالة مستعجلة. لازم تاخذه لأقرب طوارئ مستشفى توا وما تستناش. ربي يحفظه."

_TEMPLATE_RE = re.compile(r"Template \(Libyan Arabic\):\s*\n\s*>\s*\"([^\"]+)\"")


def load_emergency_template(guardrails_text: str) -> str:
    """Extract the approved Libyan emergency template from the guardrails markdown."""
    match = _TEMPLATE_RE.search(guardrails_text or "")
    if not match:
        logger.error("Emergency template not found in safety_guardrails.md; using default.")
        return DEFAULT_EMERGENCY_REPLY
    return match.group(1).strip()


def build_emergency_reply(
    template: str,
    emergency_number: str | None = None,
    nearest_facility: str | None = None,
) -> str:
    """Compose the final emergency message. Unavailable values are omitted, never invented."""
    lines = [template]
    if emergency_number:
        lines.append(f"رقم الطوارئ: {emergency_number}")
    if nearest_facility:
        lines.append(f"أقرب طوارئ: {nearest_facility}")
    return "\n".join(lines)
