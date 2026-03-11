INR → USD Daily FX Transaction System
This is a great product design challenge. Let me break it down across key dimensions:

Understanding the Problem
Scale: 1–10 transactions/day × $10K USD each = up to $100K USD/day (~₹83L/day)
This puts you in a meaningful but not ultra-high-frequency tier — the solution doesn't need to be HFT infrastructure, but it does need reliability, compliance, and cost efficiency.

Core Product/System Components
1. FX Rate Engine

Integrate with a rate aggregator (e.g., Wise API, Currencycloud, or direct bank APIs like ICICI/HDFC Forex) to get live mid-market rates
Build a rate lock mechanism — user sees a rate, you lock it for 60–120 seconds before execution
Store rate history for reconciliation and audit

2. Transaction Orchestration Layer

Queue-based architecture (e.g., SQS or a simple job queue) — even at 10 tx/day, idempotency and retry logic matter enormously for money movement
State machine per transaction: initiated → rate_locked → compliance_check → funds_debited → fx_executed → funds_credited → settled
Dead letter queues for failed transactions with alerting

3. Compliance & KYC/AML Layer (non-negotiable for RBI rules)

LRS (Liberalized Remittance Scheme) tracking — $250K/year cap per individual
FEMA compliance — purpose codes required for each transaction
KYC document storage and refresh workflows
TCS (Tax Collected at Source) calculation — 0.5–20% depending on purpose
SAR filing hooks if needed

4. Banking/Payment Rail Integration

INR leg: NEFT/RTGS/IMPS for debit from customer's Indian bank account
USD leg: SWIFT for international transfers, or Wise/Currencycloud for cheaper corridors
Consider nostro account management if you're building for a licensed entity

5. Reconciliation & Ledger

Double-entry ledger for every movement
Daily reconciliation jobs comparing your internal ledger vs. bank statements
Tolerance thresholds and exception workflows for mismatches


Architecture Recommendation
User/API → Rate Service → Compliance Engine
                ↓
         Transaction Queue (idempotent)
                ↓
    [INR Debit] → [FX Execution] → [USD Credit]
                ↓
        Ledger + Reconciliation
                ↓
     Reporting / Audit Trail / TCS filings