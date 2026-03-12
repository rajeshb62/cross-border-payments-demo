# USD Transfer Integration Comparison

Comparison of outbound USD delivery options for the final leg of the INR→USD remittance pipeline (post FX conversion), evaluated against a traditional SWIFT wire baseline.

---

## Summary Table

| Parameter | SWIFT | TransFi | Circle | Coinbase Prime | Airwallex |
|---|---|---|---|---|---|
| **Type** | Fiat wire | Crypto rails (USDC off-ramp) | Fiat wire | Crypto-to-fiat (USDC) | Fiat LOCAL rails |
| **Settlement speed** | 1–3 business days | 1–4 hours | Same-day to next business day | Same-day (Fedwire) to next day | Same-day to next business day |
| **Transfer fee** | $15–$45 per transfer + correspondent fees | ~0.5–1% of amount | $10–$25 flat (wire) | $10–$25 flat | $0–$3 (LOCAL) |
| **FX spread** | 0.5–2% (bank markup) | Minimal (USDC is pegged) | None (USD→USD) | None (USD→USD) | None (USD→USD) |
| **Correspondent bank hops** | 1–3 hops | None | None | None | None |
| **Beneficiary registration** | Not required | Not required (inline) | Required (`wire_id`) | Required (`counterparty_id`) | Required (`beneficiary_id`) |
| **Auth model** | N/A | API key + HMAC | Bearer token | Per-request HMAC signing | OAuth2 (30-min token) |
| **Idempotency** | Not natively supported | `reference_id` | `idempotencyKey` | `idempotency_key` | `request_id` |
| **Webhook support** | No | Yes | Yes | Yes | Yes |
| **Sandbox / test environment** | No | Yes | Yes | Yes | Yes |
| **Geographic coverage** | 200+ countries | 30+ countries | 180+ countries | 40+ countries (institutional focus) | 150+ countries |
| **Regulatory model** | Bank-regulated | Crypto MSB / VASP | NYDFS-licensed trust company | Regulated crypto exchange | EMI licensed (ASIC, FCA, etc.) |
| **Crypto exposure** | None | Yes — USDC in transit | None | Yes — USDC in transit | None |
| **Integration complexity** | High (SWIFT gateway, MT103) | Low (single API call) | Medium (2-step: register + pay) | High (2-step + per-request signing) | Medium (2-step + OAuth2 refresh) |

---

## Parameter Deep-Dives

### 1. Speed

| Provider | Typical Delivery | Notes |
|---|---|---|
| **SWIFT** | 1–3 business days | Add 1 day per correspondent bank hop; cut-off times apply |
| **TransFi** | 1–4 hours | USDC settles on-chain in seconds; off-ramp to fiat adds processing time |
| **Circle** | Same-day (US domestic) / next business day (international) | Fedwire cut-off is 18:00 ET; ACH is next-day |
| **Coinbase Prime** | Same-day (Fedwire) / next day (ACH) | Primarily US-focused; international depends on local partners |
| **Airwallex** | Same-day to next business day | LOCAL rail at destination (ACH for US, Faster Payments for UK, SEPA for EU); no SWIFT hop |

**Winner: TransFi** for raw speed. **Airwallex** for speed + purely fiat (no crypto exposure).

---

### 2. Cost

| Provider | Fee Structure | Estimated Cost on $1,000 transfer |
|---|---|---|
| **SWIFT** | $15–$45 flat + $10–$30 per correspondent bank + 0.5–2% FX spread | $40–$100+ |
| **TransFi** | ~0.5–1% of transfer amount | $5–$10 |
| **Circle** | $10–$25 flat per wire payout | $10–$25 |
| **Coinbase Prime** | $10–$25 flat + volume-based tier discounts | $10–$25 |
| **Airwallex** | $0–$3 for LOCAL payments; $15–$25 for SWIFT fallback | $0–$3 |

**Winner: Airwallex LOCAL** for cost. TransFi is competitive for larger amounts where flat fees dominate.

---

### 3. Integration Complexity

**SWIFT**
- Requires a SWIFT gateway provider (e.g. SWIFT gpi) or a banking partner
- Messages formatted as MT103 or MX (ISO 20022)
- No standard REST API; implementation is bespoke per bank

**TransFi**
- Simplest integration: single `POST /payouts` call with beneficiary details inline
- No pre-registration step
- USDC handled internally — you deal in USD amounts only

**Circle**
- Two-step: register bank account (`wire_id`) once, then `POST /payouts` per transaction
- `wire_id` cached on `Beneficiary` row — first payment to a beneficiary takes slightly longer
- Simple Bearer token auth

**Coinbase Prime**
- Two-step: register counterparty once, then `POST /withdrawals`
- Most complex auth: every HTTP request requires a fresh HMAC-SHA256 signature over `timestamp + method + path + body`
- Best suited for institutions that already have a Prime relationship

**Airwallex**
- Two-step: register beneficiary once, then `POST /payments/create`
- OAuth2 token with 30-minute TTL — simpler than per-request signing but requires token refresh logic
- `payment_method="LOCAL"` explicitly selects domestic rails over SWIFT

---

### 4. Crypto Exposure

A key operational and compliance consideration for an RBI-regulated remittance business:

| Provider | Crypto in transit? | Risk |
|---|---|---|
| **SWIFT** | No | None |
| **TransFi** | Yes — USDC on Polygon/Ethereum/Tron | USDC depeg risk (minimal but non-zero); blockchain congestion risk; VASP compliance obligations |
| **Circle** | No | None — Circle holds USD internally; no on-chain step visible to you |
| **Coinbase Prime** | Depends on configuration | Can be structured as USD-only; Prime is primarily crypto-native |
| **Airwallex** | No | None — pure fiat throughout |

For an RBI LRS remittance platform, **fiat-only providers (Circle, Airwallex) are lower-risk** from a regulatory standpoint. Using USDC in transit could trigger FEMA provisions on crypto asset transfers.

---

### 5. Geographic Coverage

| Provider | Key Markets | Gaps |
|---|---|---|
| **SWIFT** | 200+ countries | Sanctioned countries (OFAC), but otherwise universal |
| **TransFi** | South/Southeast Asia, Middle East, Africa focus | Limited Western Europe coverage |
| **Circle** | 180+ countries | Some emerging markets require a SWIFT fallback |
| **Coinbase Prime** | US, EU, UK, select APAC | Not designed for broad emerging market coverage |
| **Airwallex** | 150+ countries with LOCAL rails; 200+ with SWIFT fallback | Full LOCAL coverage in US, EU, UK, AU, SG, HK; SWIFT used elsewhere |

---

### 6. Regulatory & Compliance Posture

| Provider | Regulation | Relevant for India LRS |
|---|---|---|
| **SWIFT** | Bank-regulated end-to-end | Fully compatible with RBI/FEMA; standard AD-1 bank channel |
| **TransFi** | Crypto MSB/VASP licences | Crypto transfer leg may require additional RBI clarity |
| **Circle** | NYDFS-licensed trust company; e-money licences in EU | Solid; USD treated as fiat deposit |
| **Coinbase Prime** | US-regulated crypto exchange; institutional | Crypto-adjacent; may need RBI review |
| **Airwallex** | EMI licences (ASIC, FCA, MAS, etc.); non-crypto | Cleanest regulatory fit for LRS; treated as a payment institution |

---

## Recommendation for This System

Given the goals of **speed**, **cost reduction**, and **regulatory simplicity** for an INR→USD LRS remittance platform:

1. **Primary choice: Airwallex**
   - Lowest cost ($0–$3 per LOCAL payment)
   - No crypto exposure — clean FEMA/RBI compliance posture
   - LOCAL rails at destination eliminate SWIFT hops
   - 150+ country coverage covers most LRS use cases (education in US/UK/AU, medical, family support)

2. **Fallback / niche: TransFi**
   - Better for corridors where Airwallex doesn't have LOCAL coverage
   - Faster settlement (hours vs same-day) for time-sensitive transfers
   - Requires careful handling of USDC-in-transit for RBI compliance

3. **Avoid for this use case: Coinbase Prime**
   - Integration complexity (per-request signing) not justified for fiat-primary use case
   - Crypto-native platform is a regulatory overhead for an LRS business

4. **Circle is a viable alternative to Airwallex** if you already have a Circle account and US-only beneficiary reach is sufficient.
