# EximPe — Cross-Border Payments for Foreign Merchants

## Problem Statement

Foreign merchants (outside India) want to collect payments from Indian customers without needing an Indian legal entity. Indian customers pay using familiar local methods (UPI, NetBanking, card). EximPe sits in the middle: collecting INR on behalf of the merchant, converting it to their preferred settlement currency, and wiring it to their offshore bank account.

**Flow:** Indian customer pays in INR → EximPe collects via virtual account → converts to merchant's settlement currency → settles to merchant's offshore account.

---

## Target Users

- **Foreign merchants**: SaaS companies, marketplaces, retailers, and service providers outside India who have Indian customers but no Indian banking presence.
- **Indian customers**: Pay in INR via UPI, NetBanking, or card — no awareness of the FX or cross-border complexity.

---

## Core System Components

### 1. Merchant Onboarding
- Self-serve merchant registration with country, settlement currency, and bank details
- Auto-provisioning of a virtual Indian bank account (INR account number + IFSC) per merchant
- KYC status tracking (pending_kyc → active → suspended)
- Settlement currencies supported: USD, EUR, GBP, SGD, AED, HKD, CNH

### 2. Payment Collection
- Indian customers pay INR into the merchant's virtual account
- Payment methods: UPI, NetBanking, card
- FEMA purpose codes required per transaction (e.g. P0802 for software/IT services)
- Platform fee: 1.5% of INR amount
- TCS (Tax Collected at Source) calculated per purpose code:
  - P0802 (software/IT exports): 0%
  - P1007 (education): 0.5%
  - Others: 0% below ₹7L, 20% on amount above ₹7L threshold

### 3. FX Conversion
- Live rates fetched from frankfurter.app, cached in Postgres (refreshed every 60s)
- Settlement amount = (INR amount − fee − TCS) / FX rate
- Rate used is recorded on each transaction for audit

### 4. Settlement
- Converted amount wired to merchant's offshore bank account in their settlement currency
- Settlement pipeline: initiated → inr_collected → fx_converted → settled
- All steps are async via Celery workers

### 5. Reconciliation
- Every settled transaction generates a ReconciliationLog entry
- Expected vs actual settlement amount tracked
- Periodic background job (every 60s) audits settled transactions from last 24h
- Status: matched / mismatch / pending

---

## Architecture

```
Indian Customer
      |
      | (UPI / NetBanking / Card)
      ↓
Virtual INR Account (per merchant)
      |
      ↓
EximPe Payment Pipeline (Celery)
      |
      ├── Simulate INR collection
      ├── Fetch live FX rate (frankfurter.app)
      ├── Deduct fee (1.5%) + TCS
      └── Compute & record settlement amount
      |
      ↓
Merchant's Offshore Bank Account
(USD / EUR / GBP / SGD / AED / HKD / CNH)
      |
      ↓
Reconciliation Log
```

---

## API Surface

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/merchants` | Onboard a new merchant + auto-create virtual account |
| GET | `/merchants/{id}` | Get merchant profile + virtual account details |
| GET | `/merchants` | List all merchants |
| POST | `/payments` | Initiate a payment (triggers async pipeline) |
| GET | `/payments/{transaction_id}` | Get transaction status + settlement details |
| GET | `/payments/merchant/{merchant_id}` | List all transactions for a merchant |
| GET | `/fx-rates` | Current cached INR→X rates for all 7 currencies |
| GET | `/reconciliation` | Recent reconciliation log entries |

---

## Tech Stack

- **API**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 15 via SQLAlchemy asyncio + Alembic migrations
- **Queue / Workers**: Celery + Redis
- **FX Data**: frankfurter.app (free, no auth required)
- **Testing**: pytest + SQLite in-memory + fakeredis (no Docker needed)
- **Infrastructure**: Docker Compose (Postgres, Redis, API, Celery worker, Celery beat)

---

## Demo Scope (explicit simplifications)

- No real UPI/bank API calls — INR collection is simulated
- No real FX execution or wire transfers — settlement is computed, not executed
- No auth/JWT
- No webhook delivery to merchants
- No frontend
- No real KYC document handling (status field only)
- No rate-lock timeout
- FX variance in reconciliation is randomly simulated (±0.1%)

Each service file contains `# DEMO SIMPLIFICATION` and `# PRODUCTION TODO` comments documenting the gap between demo and production behaviour.

---

## Seed Data

Three demo merchants pre-loaded:

| Merchant | Country | Settlement Currency | Purpose Code |
|----------|---------|-------------------|--------------|
| Acme SaaS | US | USD | P0802 |
| Berlin Marketplace | DE | EUR | P0802 |
| Singapore Retailer | SG | SGD | P1007 |

Run `python seeds.py` to load them with 5 sample transactions in various states.
