# CrossBorderApp — Cross-Border Payments Demo

A FastAPI backend demo modelling [CrossBorderApp](https://cross_border_app.com), an **RBI PA-CB licensed cross-border payment aggregator**.

Foreign merchants (Singapore, UAE, US, UK, HK, etc.) collect INR payments from Indian customers via UPI, NetBanking, and cards — and receive settlement in their preferred foreign currency. CrossBorderApp operates under RBI's **OPGSP / PA-CB** regulatory model. **This is not an LRS / outward remittance product.**

---

## What CrossBorderApp Does

```
Indian Customer
      │  pays INR via UPI / NetBanking / Card
      ▼
CrossBorderApp Virtual Account  (unique INR account per merchant, IFSC: CROSS_BORDER_APP0001)
      │  confirms UPI payment, locks FX rate
      ▼
CrossBorderApp FX Engine        (live rates from frankfurter.app, 120s rate lock)
      │  deducts 1.5% platform fee
      ▼
Merchant Offshore Bank  (USD / SGD / AED / GBP / HKD)
      │  T+2 settlement
      ▼
Reconciliation Log
```

---

## Regulatory Model

| | CrossBorderApp (this demo) | LRS / Outward Remittance |
|---|---|---|
| **Regulation** | RBI PA-CB / OPGSP | RBI LRS |
| **Who sends money** | Foreign merchant collects from India | Indian individual sends abroad |
| **Per-transaction cap** | **USD 10,000** (OPGSP limit) | USD 250,000/year |
| **TCS** | Not applicable | 0.5–20% depending on purpose |
| **Indian entity needed** | No — merchant is foreign | Sender is Indian |

---

## Payment Flow

1. **Merchant onboards** via `POST /merchants/onboard` → KYB review starts (demo: auto-approves in 10s)
2. **Payment intent created** via `POST /payments` → returns UPI deep link, QR payload, VPA, FX rate locked for 120s
3. **Indian customer pays** via UPI (scans QR or clicks deep link)
4. **UPI webhook received** at `POST /payments/webhook/upi` (HMAC-SHA256 signed) → triggers settlement pipeline
5. **Settlement computed**: INR collected ÷ locked FX rate − 1.5% fee → credited to merchant in T+2
6. **Reconciliation logged** with expected vs actual settlement amount

---

## Settlement Currencies

| Currency | Corridor |
|----------|---------|
| USD | United States |
| SGD | Singapore |
| AED | UAE |
| GBP | United Kingdom |
| HKD | Hong Kong |

---

## OPGSP Per-Transaction Cap

Each payment is capped at **USD 10,000 equivalent** per RBI OPGSP guidelines. Attempts above this return:

```json
{"error": "opgsp_limit_exceeded", "max_usd": 10000, "max_inr": 835000}
```

---

## Running Locally

```bash
# Start all services
docker compose up --build -d

# Apply migrations
docker compose exec api alembic upgrade head

# Load seed data (3 merchants + 5 transactions)
docker compose exec api python seeds.py

# Open interactive API explorer
open http://localhost:8000/docs
```

**Run tests (no Docker needed):**
```bash
.venv/bin/pytest tests/ -v   # 16/16 pass — SQLite in-memory + fakeredis
```

---

## API Endpoints

### Merchants
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/merchants/onboard` | Onboard foreign merchant (KYB flow, starts PENDING) |
| `POST` | `/merchants` | Create merchant (auto-approved, for seeding/testing) |
| `GET` | `/merchants/{id}` | Merchant profile + virtual account details |
| `GET` | `/merchants` | List all merchants |

### Payments
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/payments` | Create payment intent — returns UPI deep link + QR + locked FX rate |
| `POST` | `/payments/webhook/upi` | Receive UPI payment notification (HMAC-signed) |
| `GET` | `/payments/{id}` | Full transaction detail |
| `GET` | `/payments/{id}/status` | Lightweight status poll for customer display |
| `GET` | `/payments/merchant/{id}` | All transactions for a merchant |

### FX & Reconciliation
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/fx-rates` | Cached INR→X rates for all 5 settlement currencies |
| `GET` | `/reconciliation` | Recent reconciliation log entries |

---

## Tech Stack

- **API**: FastAPI + Python 3.11
- **DB**: PostgreSQL 15 · SQLAlchemy asyncio · Alembic
- **Queue**: Celery + Redis (beat: FX refresh every 60s, reconciliation every 60s)
- **FX Data**: [frankfurter.app](https://www.frankfurter.app) (free, no auth) with mock fallbacks
- **Tests**: pytest · SQLite in-memory · fakeredis

---

## Demo Simplifications

Each service file includes `# DEMO SIMPLIFICATION` and `# PRODUCTION TODO` comments. Key gaps:

- No real UPI/bank API calls — collection is simulated / webhook-driven
- No real wire transfers — settlement amount is computed, not executed
- KYB review is auto-approved after 10s (production: 48h manual review)
- FX variance in reconciliation is randomly simulated (±0.1%)
- No auth/JWT, no webhooks to merchants, no frontend
