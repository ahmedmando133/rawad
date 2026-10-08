import re

def normalize_arabic(text: str) -> str:
    """توحيد الحروف العربية وتجاهل المسافات والتشكيل لضمان دقة الـ Matching"""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[أإآ]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'[يى]', 'ي', text)
    text = re.sub(r'[\u064B-\u065F]', '', text) # إزالة التشكيل
    text = re.sub(r'[^\w\s]', '', text) # إزالة علامات الترقيم
    return text.strip()