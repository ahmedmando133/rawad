# Pediatrician AI Assistant — Facebook Page & Messenger (Libya)

![CI](https://github.com/ahmedmando133/rawad/actions/workflows/ci.yml/badge.svg)

A production-ready AI-powered Facebook Page and Messenger Assistant for **Dr. Rawad Shehima (الدكتور رواد شحيمة)** at **Al-Ribat Polyclinic (مجمع عيادات الرباط)** in Tajoura, Tripoli, Libya.

Built with **FastAPI**, **Google Gemini** (active conversational engine), **SQLite**, and the **Meta Graph API**. An optional **Anthropic Claude** engine is also supported and can be enabled via configuration.

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
                   │  Layer 3: LLM Conversational Engine          │
                   │  Engine:  Gemini (gemini-3.5-flash)          │
                   │  Optional: Claude (switch via AI_PROVIDER)   │
                   │  Grounded in Libyan Brand Voice & Profile    │
                   └──────────────────────────────────────────────┘
```

| Layer | Responsibility | Token Consumption |
|---|---|---|
| **Layer 1: Safety Filter** (`core/safety_filter.py`) | Detects 10 pediatric red flags (breathing, cyanosis, seizures, choking, dehydration, etc.). Bypasses LLM completely for instant life-safety guidance. | **0 Tokens** |
| **Layer 2: Intent Router** (`core/intent_router.py` & `core/database.py`) | Intercepts routine queries (location, working hours, phone, fees, doctor title) and answers directly from SQLite DB. | **0 Tokens** |
| **Layer 3: LLM Engine** (`core/ai_engine.py` + `core/llm_provider.py`) | Provides warm, conversational pediatric prevention advice in natural Libyan Arabic. Gemini is the active engine; Claude can be enabled as primary or fallback. | **Only when needed** |

---

## Project Structure

```
c:\antigravity learning
├── api/
│   ├── main.py              # FastAPI app, lifespan, CORS, health checks
│   └── webhook.py           # Meta Webhook (GET verification + POST background processing)
├── core/
│   ├── ai_engine.py         # Layer 3 orchestration: safety → router → LLM
│   ├── llm_provider.py      # Pluggable engines (Claude / Gemini) + fallbacks
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
│   ├── test_llm_provider.py # Provider selection & message-format unit tests
│   └── run_live_scenarios.py# Live guardrail & dialect test runner
├── requirements.txt         # Dependencies
├── requirements-dev.txt     # Dev/test dependencies (pytest)
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

# Meta App Secret (App Settings -> Basic). Used to verify webhook signatures.
META_APP_SECRET=your_meta_app_secret_here

# Custom secret verify token you choose (e.g., rawad_clinic_secret_2026)
META_VERIFY_TOKEN=rawad_clinic_secret_2026

# --- AI Provider (Layer 3 conversational engine) ---
AI_PROVIDER=gemini               # gemini | claude | auto
AI_FALLBACK_PROVIDER=            # optional: gemini | claude

# Google Gemini (active engine)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACK_MODEL=gemini-flash-latest

# Anthropic Claude (optional alternative engine)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
CLAUDE_MODEL=claude-sonnet-5-5
CLAUDE_FALLBACK_MODEL=claude-haiku-5-5
CLAUDE_EFFORT=low              # low | medium | high | xhigh | max
```

> **Switching engines**: set `AI_PROVIDER` to `gemini`, `claude`, or `auto`
> (`auto` = Claude when `ANTHROPIC_API_KEY` is set, else Gemini).
> Add `AI_FALLBACK_PROVIDER=gemini` to keep a second engine as a safety net.
> All keys are read from the environment only and are never logged.

### 2. Start the FastAPI Server
```powershell
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```
Check health:
```powershell
curl http://localhost:8000/health
```

### 3. Run the Test Suite
```powershell
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```
The suite is **hermetic**: it needs no real API keys and makes no network calls,
so it passes with or without a `.env`. It runs automatically on every push and
pull request via GitHub Actions (`.github/workflows/ci.yml`) across Python
3.10, 3.11 and 3.12.

---

## Security Notes

- **Webhook signature verification**: incoming `POST /webhook` requests are validated
  against Meta's `X-Hub-Signature-256` header using `META_APP_SECRET` (HMAC-SHA256).
  Requests with a missing or invalid signature are rejected with `403`.
  If `META_APP_SECRET` is not set, verification is skipped and a warning is logged —
  **always set it in production**.
- **CORS**: closed by default. Set `CORS_ALLOW_ORIGINS` (comma-separated) only if a
  browser dashboard needs to call the API.
- **Provider API keys** (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`): read from the
  environment only, never hard-coded, never logged. On Render they are declared
  with `sync: false` so they are entered in the dashboard, not committed.
- **Secrets**: `.env` is git-ignored. Never commit real tokens.

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
