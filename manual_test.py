from core.ai_engine import PediatricianAIAssistant
from dotenv import load_dotenv

# تحميل المفتاح من ملف .env
load_dotenv()

bot = PediatricianAIAssistant()

print("--- بدء الاختبار ---")

# سيناريو 1: حجز عادي (سيعتمد على Gemini)
print("\nUser: السلام عليكم، نبي نحجز موعد لولدي")
print("Bot:", bot.generate_reply("user_1", "السلام عليكم، نبي نحجز موعد لولدي"))

# سيناريو 2: طوارئ (سيلتقطها الفلتر ولن يكلم Gemini)
print("\nUser: ولدي حرارته 40 ومش قادر يتنفس ولونه ازرق")
print("Bot:", bot.generate_reply("user_2", "ولدي حرارته 40 ومش قادر يتنفس ولونه ازرق"))