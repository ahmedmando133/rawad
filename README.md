# Pediatrician AI Assistant — Facebook Page & Messenger (Libya)

A production-ready AI-powered Facebook Page and Messenger Assistant for **Dr. Rawad Shehima (الدكتور رواد شحيمة)** at **Al-Ribat Polyclinic (مجمع عيادات الرباط)** in Tajoura, Tripoli, Libya.

Built with **FastAPI**, **Google Gemini (3.8 & 3.5 Flash)**, **SQLite**, and the **Meta Graph API**.

> ⚠️ **Clinical Safety Disclaimer**: This assistant is **not** a substitute for an in-person medical diagnosis. It strictly handles administrative questions (location, working hours, booking, contact), general non-diagnostic pediatric guidance, and instantly escalates any urgent symptoms (red flags) directly to hospital emergency departments.

---

## 3-Layer Hybrid Architecture (Zero-Token Optimized)

```
                            [ User Message from Messenger ]
                                          │
                                          ▼
                   ┌──────────────────────────────────────────────┐
                   │  Layer 1: Pre-LLM Emergency Filter           │
                   │  (Regex + Arabic Normalization + Guardrails) │
                   └──────────────────────┬───────────────────────┘
                                          │
                 [ Emergency Detected? ] ─┼──▶ YES ──▶ Return Immediate ER Reply
                                          │             (0 Tokens · Sub-millisecond)
                                          ▼ NO
                   ┌──────────────────────────────────────────────┐
                   │  Layer 2: Zero-Token Intent Router           │
                   │  (SQLite Database · Clinic Facts & FAQs)     │
                   └──────────────────────┬───────────────────────┘
                                          │
                 [ Routine Admin Match? ] ─┼──▶ YES ──▶ Return Verified Fact
                                          │             (0 Tokens · No Hallucination)
                                          ▼ NO (Clinical / General Pediatric)
                   ┌──────────────────────────────────────────────┐
                   │  Layer 3: Gemini Conversational Engine       │
                   │  Primary: gemini-3.8-flash                   │
                   │  Fallback: gemini-3.5-flash                  │
                   │  Grounded in Libyan Brand Voice & Profile    │
                   └──────────────────────────────────────────────┘
```

| Layer | Responsibility | Token Consumption |
|---|---|---|
| **Layer 1: Safety Filter** (`core/safety_filter.py`) | Detects 10 pediatric red flags (breathing, cyanosis, seizures, choking, dehydration, etc.). Bypasses LLM completely for instant life-safety guidance. | **0 Tokens** |
| **Layer 2: Intent Router** (`core/intent_router.py` & `core/database.py`) | Intercepts routine queries (location, working hours, phone, fees, doctor title) and answers directly from SQLite DB. | **0 Tokens** |
| **Layer 3: Gemini Engine** (`core/ai_engine.py`) | Provides warm, conversational pediatric prevention advice in natural Libyan Arabic with automatic fallback model on load spikes. | **Only when needed** |

---

## Project Structure

```
c:\antigravity learning
├── api/
│   ├── main.py              # FastAPI app, lifespan, CORS, health checks
│   └── webhook.py           # Meta Webhook (GET verification + POST background processing)
├── core/
│   ├── ai_engine.py         # Multi-model Gemini orchestration (3.8 + 3.5 fallback)
│   ├── database.py          # SQLite persistence for facts, FAQs, and chat sessions
│   ├── intent_router.py     # Deterministic regex router for zero-token replies
│   ├── messenger.py         # Async Meta Graph API client (typing indicator + send)
│   └── safety_filter.py     # Pre-LLM red flag detector & Arabic normalizer
├── data/
│   └── clinic.db            # SQLite database file
├── knowledge/
│   ├── brand_voice.md       # Libyan dialect persona & tone rules
│   ├── conversation_rules.md# WhatsApp-style chat brevity & constraints
│   ├── doctor_profile.yaml  # Verified facts for Dr. Rawad Shehima & clinic
│   ├── faqs.json            # Doctor-approved FAQs
│   └── safety_guardrails.md # Non-negotiable clinical safety constraints
├── tests/
│   ├── test_api.py          # Integration tests for FastAPI endpoints
│   └── run_live_scenarios.py# Live guardrail & dialect test runner
├── requirements.txt         # Dependencies
├── .env.example             # Configuration template
└── README.md
```

---

## Setup & Running Locally

### 1. Configure Environment
Copy `.env.example` to `.env` and configure:
```env
# Meta Page Access Token (from Meta for Developers App -> Messenger API Setup)
META_PAGE_ACCESS_TOKEN=your_page_access_token_here

# Custom secret verify token you choose (e.g., rawad_clinic_secret_2026)
META_VERIFY_TOKEN=rawad_clinic_secret_2026

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODEL=gemini-3.5-flash
```

### 2. Start the FastAPI Server
```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
Check health:
```powershell
curl http://localhost:8000/health
```

---

## Connecting with Meta Facebook Page

1. **Expose your local server to the Internet** (e.g. via `ngrok` or `localtunnel`):
   ```bash
   ngrok http 8000
   ```
   Copy the HTTPS forwarding URL (e.g. `https://xyz.ngrok-free.app`).

2. **Configure Webhook in Meta for Developers**:
   * Go to **Meta for Developers** -> Your App -> **Messenger** -> **Webhooks**.
   * Callback URL: `https://xyz.ngrok-free.app/webhook`
   * Verify Token: Enter the exact value you set in `META_VERIFY_TOKEN`.
   * Click **Verify and Save**.

3. **Subscribe to Page Events**:
   * Under Webhook Page Subscriptions, subscribe to:
     * `messages`
     * `messaging_postbacks` (optional)

4. **Test on Messenger**:
   * Send a message to Dr. Rawad Shehima's Facebook page from your personal account:
     * *"وين مكان العيادة؟"* ➡️ Instant zero-token reply.
     * *"امتى تفتحوا؟"* ➡️ Instant zero-token working hours.
     * *"ولدي حرارته 40 وصدره يصفر"* ➡️ Instant emergency escalation.
