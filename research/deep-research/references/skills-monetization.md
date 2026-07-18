# AI Skills Monetization — Condensed Knowledge Bank

> Sourced from deep research (01 Jul 2026, 13 sources, 3 rounds). Full dossier: `~/research/2026-07-01-skills-monetization-dossier.md`

## Marketplaces

| Platform | Type | Fee/Split | Notes |
|---|---|---|---|
| Agensi | Developer (paid SKILL.md) | 30% platform fee, 70% to creator | 8-point security scan, Stripe Connect, one-liner install. Sweet spot $5–$15 |
| Claudate | Developer (directory) | — | 150K+ skills listed |
| GPT Store | Consumer | Usage rev-share | 800M+ users, weak enterprise procurement |
| Salesforce AgentExchange | Enterprise | ~20–30% | $800M ARR, 10K+ apps |
| Microsoft Marketplace | Enterprise | 3% flat | 100% counts toward Azure commitments |
| Google Agentspace | Enterprise | Rev-share | Gemini Enterprise native |
| AWS Marketplace | Enterprise | Varies | Unified billing/IAM, private offers |

## What Sells (top 5 categories)

1. Testing skills (framework-specific: pytest fixtures, Jest async)
2. Code review skills (OWASP security, team style)
3. Framework starters (Next.js, Django, opinionated defaults)
4. DevOps skills (Dockerfiles, GitHub Actions, K8s manifests)
5. Documentation skills (PR descriptions, changelogs, house style)

**Core pattern:** Skills encoding specific opinions requiring multiple prompts to extract. Generic prompt wrappers do NOT sell.

**What does NOT sell:** Simple prompt wrappers, skills overlapping official provider offerings, skills duplicating agent's built-in strengths, skills with unexplained external deps.

## Pricing

| Model | Range | Best For |
|---|---|---|
| Free | $0 | Lead gen, reputation |
| One-time | $5–$15 (up to $25 specialized) | Individual developers |
| Bundle | $15–$25 | Cross-selling related skills |
| Subscription | $9–$249/mo | Ongoing updates |
| Enterprise license | $500–$50K/year | Firms, regulated industries |
| White-label | $2K setup + $500/mo/client | Agencies, 80–90% margins |
| Managed service | $500–$2K/mo | Hosted + maintained |

**Rule of thumb:** Price at ~cost of 15 minutes of senior developer time.

**Top earners:** $500–$3,000/month recurring. **Median:** <$50/month (revenue concentrates in top ~10%).

## IP Protection (ranked for skills)

1. **Trade Secret** ⭐ — Best for unpublished skills. Perpetual, no registration, no disclosure. Use NDAs, access control, employment agreements.
2. **Contractual Licensing** ⭐ — Best for sold skills. No redistribution, no reverse engineering clauses in EULA.
3. **Copyright** — Good for compendiums. Automatic for human-authored literary works. AI-generated content has no copyright (March 2026 SCOTUS ruling).
4. **Patent** — Poor for individual skills. 20-year term, public disclosure, §101/Alice challenges.
5. **Trademark** — Brand only, not content.

## Technical Gatekeeping

### Content Fingerprinting (Gen Digital Skill ID)
- Adapts git's tree hashing: normalize paths → SHA-256 each file → hash sorted tree entries
- Stable across ZIP packaging, OS, Unicode differences
- Use for: allowlisting, dedup, version tracking, cache keys

### Cryptographic Signing (NVIDIA Verified Skills)
- OpenSSF Model Signing, CMS SignedData (PKCS #7)
- Detached `skill.oms.sig` file, covers every file in skill dir
- 8-step flow: source → review → scan (SkillSpector) → evaluate → skill card → sign → catalog → sync
- SkillSpector checks: vulnerable deps, prompt injection, trigger abuse, excessive agency, tool poisoning

### License Key APIs

| Platform | Key Feature | Best For |
|---|---|---|
| Keygen | Full licensing API, SOC 2, self-hostable (CE free) | Full-featured licensing |
| Lemon Squeezy | MoR + license keys, subscription-linked, global tax | Combined payment + licensing |
| Gumroad | Payment + basic keys (no device locking) | Simple sales only |
| LicenseSeat | HWID locking, seat management, offline validation | Serious anti-piracy |

**Critical:** Gumroad/Lemon Squeezy keys are "just strings" — no device validation, no piracy prevention. Use Keygen or LicenseSeat for real protection.

### Ed25519 Signed License Tokens (custom build)
- Token: `<base64url(payload_json)>.<base64url(ed25519_signature)>`
- Payload: client_id, expiry, features, license_id, max_offline_days
- Hybrid: offline signature check (always) + online revocation (when reachable)
- Offline grace window for flaky connections
- No-op when unconfigured (dev/local use)
- Pure stdlib + `cryptography` library

### Token-Gated Download Flow
1. Customer pays (Lemon Squeezy/Gumroad/Stripe)
2. Webhook → licensing service generates key
3. Key emailed to buyer
4. Install script validates key → registers device → downloads signed skill bundle
5. Skill files never on public URL — only delivered after validation

### Buyer Fingerprinting (Steganographic)
- `skill-license-fingerprinter` ($7 on Agensi) embeds invisible buyer fingerprints
- Post-leak attribution: identifies the original buyer from a leaked copy

## Six Distribution-to-Revenue Patterns

1. Public Registry → Inbound Leads (free listing → consulting/enterprise)
2. Digital Product Sale (zip/private repo via Gumroad/Lemon Squeezy)
3. Open Core (free baseline + paid advanced packs)
4. Services + Audits (skill as delivery accelerator for day-rate revenue)
5. Education/Cohorts (skill as course lab)
6. Third-Party Marketplace (Agensi/GPT Store, 70–85% rev share)

## Enterprise Buyer's 5-Question Filter

1. What's in the permission manifest? (least privilege)
2. Is the audit trail complete? (every tool call logged)
3. Supply chain? (signed bundles, pinned versions, CVE history)
4. Runtime isolation? (dedicated tenant/VPC, default-deny egress)
5. Kill switch? (one-click agent-level revocation)

## Market Sizing

- AI agent market: $7.6B (2025) → $47B (2030 projected)
- Gartner: 40% of enterprise apps will include AI agents by end 2026
- McKinsey: $2.9T US economic value/year by 2030
- Bessemer: 43% of SaaS companies use hybrid pricing in 2026

## Open-Core Licensing Strategy

Publish baseline under permissive license (MIT, Apache 2.0) → drive adoption → charge for advanced packs (industry variants, compliance mappings, MCP scripts). Mirrors open-core software GTM.

## Key Legal Points

- AI-generated content has NO copyright owner (US, March 2026 SCOTUS)
- Human-authored skill files likely qualify as literary works
- Trade secret protection is perpetual if secrecy maintained
- Contractual licensing is the most directly enforceable for sold skills
- Always include: no-reverse-engineering, no-redistribution, no-AI-training clauses in EULA