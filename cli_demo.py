"""
Local CLI demo for the Pediatrician AI Assistant.

Runs the real production pipeline end-to-end:
    Layer 1 (safety filter) -> Layer 2 (zero-token router) -> Layer 3 (LLM).

For the scripted guardrail/dialect scenarios use:
    python -m tests.run_live_scenarios
    python -m tests.run_live_scenarios --chat
"""

from __future__ import annotations

import sys
import uuid

from dotenv import load_dotenv

from core.ai_engine import PediatricianAIAssistant

# Messenger is Unicode; make Windows consoles print Arabic/emoji correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()


def run_demo() -> int:
    print("🚀 جاري تشغيل Local Testing Demo...")
    try:
        bot = PediatricianAIAssistant()
    except RuntimeError as exc:
        print(f"خطأ في الإعداد: {exc}", file=sys.stderr)
        return 2

    print("\n" + "=" * 50)
    print(f"🤖 Bot (المحرك: {bot.model})")
    print("اكتب رسالتك (أو 'خروج' للإنهاء، و'/reset' لتفريغ المحادثة)")
    print("=" * 50 + "\n")

    user_id = f"cli-{uuid.uuid4().hex[:8]}"
    while True:
        try:
            user_message = input("\n🧑 User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if user_message.lower() in {"exit", "quit", "خروج"}:
            return 0
        if user_message == "/reset":
            bot.reset_conversation(user_id)
            print("(تم تفريغ المحادثة)")
            continue
        print(f"🤖 Bot:\n{bot.generate_reply(user_id, user_message)}")


if __name__ == "__main__":
    sys.exit(run_demo())
