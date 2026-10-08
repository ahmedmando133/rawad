from core.message_router import MessageRouter

def run_demo():
    print("🚀 جاري تشغيل Local Testing Demo...")
    router = MessageRouter()
    
    print("\n" + "="*50)
    print("🤖 Bot: هلا بيك 👋 تفضل اختار من القائمة أو اكتب سؤالك:")
    print("Buttons:", " | ".join(router.db.get("buttons", [])))
    print("="*50 + "\n")

    user_id = "test_user_1"

    while True:
        user_message = input("\n🧑 User: ")
        if user_message.lower() in ['exit', 'quit', 'خروج']:
            break
            
        result = router.handle_user_message(user_id, user_message)
        
        print(f"🤖 Bot [{result['source']}]:\n{result['reply']}")
        print(f"🔘 Options: {', '.join(result['buttons'])}")

if __name__ == "__main__":
    run_demo()