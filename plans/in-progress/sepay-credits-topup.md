# Sepay Integration — Top-Up Credits (VN Market)

## Context

The pricing page (`frontend/app/pricing/page.tsx`) is fully designed but inert: every CTA links to `/login`, no payment provider exists, the `User` model has no plan/tier field, and there is no quota enforcement. AI usage is *logged* (`AIUsageEvent`) but never gated — anyone with an account can consume unlimited LLM calls.

We want to monetize via **Sepay** (VietQR / Vietnamese bank-transfer gateway). Sepay does **not** support recurring billing, so we are pivoting from a monthly-subscription model to a **top-up credits model**: users buy credit packs via QR/bank-transfer, Sepay's webhook confirms the payment, the backend grants credits, and feature endpoints (Deep Search, Writer, paper chat, PDF upload) debit credits before running. Pricing is **displayed in USD** (no rewrite of the existing pricing page copy) but **charged in VND** at a snapshot FX rate locked at order creation.

This is phase 1 — the first phase delivers the Sepay payment loop, credit ledger, and core quota enforcement on the most expensive operations. Lab/Team seat-pooling and `.edu` student verification are deferred.

## Approach

A single integer credit balance per user. Plans become **credit packs** (one-time purchases). Add-ons are also credit packs / one-shot items. Sepay's per-order Virtual Account flow generates a unique reference code per order; the user transfers VND with that code in the description; Sepay's webhook fires; we credit the user's balance idempotently. Free-tier users get a monthly grant via a scheduled job (deferred to phase 2 — initial implementation seeds 100 free credits at signup).

### Credit denomination

- **1 credit = ~$0.01 USD equivalent** (so $8 pack ≈ 800 credits, $24 ≈ 2400 credits). This keeps the math obvious and avoids fractional units.
- Feature costs (configurable in `backend/config.py`):
  - Deep Search report: **80 credits** ($0.80) — Researcher Pro $24 = 30 reports → matches the "40 reports" tier roughly.
  - Writer output (full): **40 credits**.
  - Paper conversation message: **2 credits**.
  - PDF upload + extraction: **5 credits**.
  - Pipeline run (Searcher+Reader): **20 credits**.
- Initial values are deliberately approximate; tune after we observe real cost in `AIUsageEvent.cost_credits`.

### Credit packs (mapped from current pricing tiers)

| Pack | USD | Credits | Notes |
|---|---|---|---|
| Student | $8 | 800 | matches old Student monthly capacity |
| Researcher Pro | $24 | 2,400 | featured |
| Lab Starter | $66 (3×$22) | 6,600 | min 3-seat equivalent, single-user for now |
| Deep Search top-up | $6 | 800 (= 10 reports) | add-on |
| PDF storage bump | $4 | 600 | add-on |

Packs live in `backend/config.py` as a constant list; phase 2 can move them to a DB table if business needs change-at-runtime.

## Database changes (new Alembic revision)

New file: `backend/db/migrations/versions/<rev>_add_credits_and_payments.py`

New columns on `users`:
- `credit_balance` (Integer, default 0, server_default "0", NOT NULL)
- `country_code` (String(8), nullable) — for future routing; default `"VN"` for new signups.

New tables:

```
credit_transactions
  id              str PK
  user_id         FK users.id (CASCADE)
  delta           int           # +N for top-up/grant, -N for consumption
  balance_after   int           # snapshot for audit
  kind            str(32)       # "topup" | "consume" | "grant" | "refund" | "adjust"
  feature         str(64) NULL  # e.g. "deep_search", "writer", "pipeline_run"
  reference_id    str NULL      # FK to ai_usage_events.id or payment_orders.id
  metadata_json   JSON
  created_at      datetime
  index (user_id, created_at desc)

payment_orders
  id                  str PK
  user_id             FK users.id (CASCADE)
  pack_id             str(32)        # "student" | "pro" | "lab_starter" | "topup_deep" | "topup_storage"
  credits             int
  usd_amount          int            # cents (e.g. 800 for $8.00)
  vnd_amount          int            # whole VND
  fx_rate_usd_to_vnd  float          # snapshot
  reference_code      str(32) UNIQUE # e.g. "ORD7H4K2X"  (goes into VND transfer description)
  sepay_va_account    str(64) NULL   # virtual account number from Sepay
  sepay_va_bank_bin   str(16) NULL
  qr_payload          text NULL      # VietQR string for the QR image (cached)
  status              str(16)        # "pending" | "paid" | "expired" | "cancelled"
  sepay_transaction_id str(64) NULL UNIQUE  # idempotency key from webhook
  created_at          datetime
  paid_at             datetime NULL
  expires_at          datetime       # default created_at + 30 min
  index (user_id, created_at desc)
  index (status, expires_at)         # for sweeper job
```

`models.py` gets `User.credit_balance`, `User.country_code`, and `User.credit_transactions` / `User.payment_orders` relationships. New `CreditTransaction` and `PaymentOrder` model classes added.

## Backend code

### Config (`backend/config.py`)
Add settings:
- `sepay_api_key` (read from `SEPAY_API_KEY`)
- `sepay_webhook_api_key` (read from `SEPAY_WEBHOOK_API_KEY`) — Sepay sends this in the `Authorization: Apikey <key>` header
- `sepay_account_number` (the bank account that receives transfers)
- `sepay_account_bank_bin` (e.g. "MB", "VCB" — used in VietQR payload)
- `usd_to_vnd_rate` (float, default 25500.0; can be overridden per env)
- `credit_pack_catalog` (a `tuple[CreditPack, ...]` constant — each entry has id, name, usd_cents, credits, badge)
- Feature credit costs (`credit_cost_deep_search`, `credit_cost_writer`, etc.)

### New service modules

**`backend/services/sepay.py`** — thin Sepay client. Phase 1 only needs:
- `build_vietqr_payload(account, bank_bin, amount_vnd, description) -> str` — pure local function; VietQR can be generated client-side without an API call (uses NAPAS spec, same string format `https://qr.sepay.vn/img?...` works as a hosted image too — we will use the hosted image URL form for simplicity: `https://qr.sepay.vn/img?acc=...&bank=...&amount=...&des=...`).
- Optional: `verify_webhook_auth(request_headers) -> bool` — checks `Authorization: Apikey <SEPAY_WEBHOOK_API_KEY>`.
- Offline fallback when `SEPAY_API_KEY` is missing: return deterministic placeholders so tests run hermetically. Mirror the offline pattern in `backend/services/llm.py`.

**`backend/services/credits.py`** — atomic credit operations. Pure function signatures:
- `async credit(session, user_id, delta, kind, *, feature=None, reference_id=None, metadata=None) -> CreditTransaction` — performs `SELECT ... FOR UPDATE` on the user row (Postgres) or row-level lock equivalent, updates `credit_balance`, inserts a `CreditTransaction`. Returns the new transaction. All within the caller's session/transaction.
- `async debit(session, user_id, amount, feature, *, reference_id=None, metadata=None) -> CreditTransaction` — same as credit with negative delta; raises `InsufficientCreditsError` if `balance < amount` (HTTP 402 at the router layer).
- `async get_balance(session, user_id) -> int`.

**`backend/services/fx.py`** — `usd_cents_to_vnd(cents: int, rate: float) -> int` (round to nearest 1000 VND for clean QR amounts).

**`backend/services/payment_orders.py`** — order lifecycle:
- `async create_order(session, user, pack_id) -> PaymentOrder` — looks up pack from `credit_pack_catalog`, computes VND with snapshotted `usd_to_vnd_rate`, generates `reference_code` (random 8–10 char alphanumeric, retry on collision), generates `qr_payload` URL via `sepay.build_vietqr_payload`, persists with `status="pending"` and `expires_at = now + 30 min`.
- `async mark_order_paid(session, reference_code, sepay_transaction_id, paid_amount_vnd) -> PaymentOrder | None` — idempotent: if `sepay_transaction_id` already recorded, returns the existing order without re-crediting. Otherwise validates `paid_amount_vnd >= vnd_amount` (allow over-pay; phase 2 can refund), sets status="paid", records `sepay_transaction_id`, calls `credits.credit` for the granted credits, all in one DB transaction.
- `async expire_stale_orders(session)` — sweeper used by the cron in phase 2.

### New routers (`backend/api/routers/payments.py`, `backend/api/routers/webhooks.py`)

`backend/api/routers/payments.py` (mounted under `/payments`, requires auth):
- `GET /payments/packs` — returns the credit pack catalog (USD + computed VND at current rate).
- `POST /payments/orders` body: `{pack_id}` → `{order_id, reference_code, qr_url, vnd_amount, expires_at, status}`.
- `GET /payments/orders/{order_id}` → full order status, used by the frontend to poll.
- `GET /payments/balance` → `{credit_balance, recent_transactions[]}`.

`backend/api/routers/webhooks.py` (mounted under `/webhooks`, NO auth dependency, but verifies `Authorization: Apikey ...` header inside the handler):
- `POST /webhooks/sepay` — accepts Sepay's transaction notification payload. Sepay's webhook contract delivers fields including `id` (Sepay txn id), `gateway`, `transactionDate`, `accountNumber`, `subAccount`, `code`, `content` (the transfer description containing our `reference_code`), `transferAmount`, `transferType` ("in"|"out"), `accumulated`, `description`. Handler:
  1. Verify auth header against `sepay_webhook_api_key`. Reject 401 on mismatch.
  2. Ignore `transferType != "in"` and any payload missing `content`.
  3. Extract `reference_code` from `content` via a strict prefix/regex (`ORD[A-Z0-9]{6,12}`). If not found, return 200 with `{"matched": false}` so Sepay doesn't retry forever.
  4. Call `payment_orders.mark_order_paid(...)`. Return 200.
  5. Idempotency comes from the `sepay_transaction_id UNIQUE` constraint + the early "already-recorded" return inside `mark_order_paid`.

Register both in `backend/main.py:36-39`.

### Quota enforcement

A single helper used at every paywalled entry point — keep the change surgical, do not refactor the routers wholesale.

**`backend/api/deps.py`**: add `async def require_credits(amount: int, feature: str, *, current_user, session) -> CreditDebitGuard`. Returns a context-manager-like object with `commit(reference_id=None)` and `rollback()`. Pattern at the call site:

```python
guard = await require_credits(
    settings.credit_cost_deep_search,
    feature="deep_search",
    current_user=current_user,
    session=session,
)
try:
    run = await deep_search.run(...)
    await guard.commit(reference_id=run.id)
except Exception:
    await guard.rollback()
    raise
```

This pre-debits credits at the start of the operation (failing fast with HTTP 402 if balance is insufficient) and reverses the debit on any error before the operation completes successfully. Phase 1 wires this into the most expensive ops only:

- `POST /projects/{id}/run` (pipeline) — `pipeline_run`
- Deep Search runs in `backend/api/routers/projects.py` — `deep_search`
- `POST /projects/{id}/writer/generate` — `writer`
- `POST /projects/{id}/papers/{paper_id}/conversations/.../messages` — `paper_chat`
- PDF upload endpoint (in `projects.py`) — `pdf_upload`

Free signup grant: in `backend/api/routers/auth.py`, after a `User` is created (both email and Google paths), call `credits.credit(..., delta=100, kind="grant", metadata={"reason": "signup_bonus"})`. 100 credits ≈ 1 deep search + a few chats; enough to demo, not enough to abuse.

## Frontend changes

### Pricing page (`frontend/app/pricing/page.tsx`)

Keep all USD copy. Change CTAs from `Link href="/login"` to a client-side flow:

- If unauthenticated: redirect to `/login?next=/billing/checkout?pack=<pack_id>`.
- If authenticated: navigate to `/billing/checkout?pack=<pack_id>`.

Update existing CTA buttons (lines 405–412 area) to a new `<PlanCta plan={plan}>` client component that knows the auth state via the existing pattern used elsewhere (look at `frontend/components/Sidebar.tsx` for how auth is read; reuse the same hook).

### New page: `frontend/app/billing/checkout/page.tsx`

Auth-required. Reads `?pack=<id>` query param.
1. On mount, `POST /payments/orders {pack_id}` → render the resulting QR image (`<img src={qr_url}>`), the VND amount, the bank account, and the `reference_code` (with a copy-to-clipboard button — important so users include it in the bank app's transfer description).
2. Poll `GET /payments/orders/{id}` every 3s. On `status="paid"`, redirect to `/billing/success` with a confetti-style confirmation that shows the new balance.
3. Show a countdown to `expires_at`; allow "Generate new order" if expired.

### New page: `frontend/app/billing/page.tsx`

Auth-required. Shows current `credit_balance`, recent transactions, and links to top up.

### Sidebar / header

Add a small balance pill in `frontend/components/Sidebar.tsx` (near the existing "Plans" link): `⚡ {balance} credits` linking to `/billing`. Refresh on a polling interval (60s) and after any feature consumption.

### Insufficient-credits UX

When a feature endpoint returns HTTP 402 with body `{detail, required, balance}`, the frontend's existing error handlers in `chat/page.tsx` (search for the writer / deep search error states) should catch this code and surface a "Top up to continue — $X for Y credits" CTA pointing at `/billing/checkout?pack=topup_deep`.

## Files to change / create

**New:**
- `backend/services/sepay.py`
- `backend/services/credits.py`
- `backend/services/fx.py`
- `backend/services/payment_orders.py`
- `backend/api/routers/payments.py`
- `backend/api/routers/webhooks.py`
- `backend/db/migrations/versions/<rev>_add_credits_and_payments.py`
- `frontend/app/billing/page.tsx`
- `frontend/app/billing/checkout/page.tsx`
- `frontend/app/billing/success/page.tsx`
- `tests/test_credits.py`
- `tests/test_payment_orders.py`
- `tests/test_sepay_webhook.py`
- `tests/test_quota_enforcement.py`

**Modified:**
- `backend/config.py` — Sepay / FX / pack catalog / credit-cost settings.
- `backend/db/models.py` — `User.credit_balance`, `User.country_code`, new `CreditTransaction` and `PaymentOrder` models.
- `backend/main.py` — register `payments.router` and `webhooks.router`.
- `backend/api/deps.py` — `require_credits` guard.
- `backend/api/routers/auth.py` — signup credit grant.
- `backend/api/routers/projects.py` — wire `require_credits` into pipeline run, deep search, writer, paper chat, pdf upload.
- `frontend/app/pricing/page.tsx` — rewire CTAs to checkout flow.
- `frontend/components/Sidebar.tsx` — balance pill.
- `frontend/app/chat/page.tsx` — handle HTTP 402 with top-up CTA.
- `.env.example` — `SEPAY_API_KEY`, `SEPAY_WEBHOOK_API_KEY`, `SEPAY_ACCOUNT_NUMBER`, `SEPAY_ACCOUNT_BANK_BIN`, `USD_TO_VND_RATE`.

## Verification

### Unit / integration tests (`uv run pytest tests/ -x`)
- `test_credits.py`: balance round-trip; concurrent debit safety (parametrised on the same user); `InsufficientCreditsError` raised when balance < amount; ledger entries are insert-only and `balance_after` is monotonically consistent.
- `test_payment_orders.py`: create order computes VND from USD and snapshots rate; reference code is unique across many orders; `mark_order_paid` is idempotent (calling twice with same `sepay_transaction_id` does not double-credit).
- `test_sepay_webhook.py`: rejects requests with wrong `Authorization` header (401); ignores `transferType=out`; matches `reference_code` from `content`; returns 200 + `{matched:false}` for unknown codes (no Sepay retry storm); on success the user balance increases and a `CreditTransaction` of kind `topup` is recorded.
- `test_quota_enforcement.py`: a user with 0 credits gets HTTP 402 from `/projects/{id}/run`; on success path, credit balance decreases by exactly `credit_cost_pipeline_run`; on a mid-pipeline failure the debit is rolled back.
- Offline fallback: tests run with `SEPAY_API_KEY` unset and still pass (mirroring the existing `OPENROUTER_API_KEY`-unset pattern).

### Manual end-to-end (Sepay sandbox)
1. `cp .env.example .env`, fill `SEPAY_*` with sandbox credentials, `uv run alembic upgrade head`, `uv run uvicorn backend.main:app --reload`, and `cd frontend && npm run dev`.
2. Sign up → confirm balance is 100, ledger has a `grant` transaction.
3. Pricing page → click "Begin Researcher Pro" → checkout page renders QR + reference code.
4. In the Sepay sandbox dashboard, simulate a bank transfer with the reference code in the description.
5. Within ~3s, frontend polling flips to "paid"; balance shows 2,500 (100 grant + 2,400 pack).
6. Run a deep search → balance decreases by 80; `credit_transactions` shows a `consume` row linking to the deep-search run id.
7. Drain credits → next deep search returns HTTP 402; UI surfaces top-up CTA.
8. Verify webhook idempotency: re-fire the same Sepay payload via `curl` → balance does not change, response 200.

### Quality gates
- `uv run ruff check .`
- `uv run mypy backend/`
- `uv run pytest tests/ -x`
- Manually exercise the checkout + deep-search flow in a browser.

## Out of scope (phase 2)
- Recurring monthly free-credit grants for free-tier users (cron job / scheduled task).
- Lab/Team seat pooling (shared balance, admin invite).
- `.edu` student verification for the Student pack.
- Refund flow for over-payments.
- Admin dashboard view of payment orders & credit ledger (extension of `frontend/app/admin/usage/`).
- Locale-aware pricing display (currently still USD on the pricing page).
- Email receipts.
