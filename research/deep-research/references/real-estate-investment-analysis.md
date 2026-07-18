# Real Estate Investment Pro-Forma — Reference Guide

> Pattern for building a quantitative investment analysis when the user
> provides specific deal parameters after a deep-research report on a
> property/real estate investment question.

## When to Use

After the deep-research report is delivered, the user may provide specific
deal parameters (asking price, GFA, NFA, location). This follow-on phase
converts the qualitative research into a quantitative pro-forma using
`execute_code` for the calculations.

## Pro-Forma Construction Steps

### 1. Price Benchmarking

- Convert GFA/NFA to tsubo (÷3.3) for Japan deals
- Calculate price per sqm and per tsubo (both GFA and NFA)
- Compare against recent transaction comparables from:
  - **Cushman & Wakefield** Japan Capital Markets reports (H1/H2 annual)
    → URL pattern: `assets.cushmanwakefield.com/-/media/cw/marketbeat-pdfs/...`
  - **CBRE** Japan Investment MarketView (quarterly)
  - **Savills** Japan research articles (`savills.co.jp/research_articles/`)
  - **JLL** Japan Market Dynamics (`jll.com/en-jp/insights/market-dynamics/japan`)
- Key cap rate benchmarks (Japan, H2 2025):
  - Office (Tokyo 5W): 3.3%–4.3%
  - Hotel: 4.4%–6.2%
  - Multi-family: 3.9%–4.6%
  - Logistics: 4.3%–5.5%
  - Retail: 3.4%–5.2%

### 2. Alternative Use Modeling

Model income under multiple use scenarios:

**Office (as-is):**
- Estimate rent per tsubo/month for the submarket (NOT CBD rates for
  non-CBD locations — Koto-ku ≠ Marunouchi)
- NOI = rent × tsubo × 12 × (1 − vacancy) × (1 − opex_ratio)
- Typical vacancy: 5%, opex: 20% of effective rent

**Hotel (converted):**
- Room count = (NFA × usable_ratio) / room_size
  - usable_ratio: ~60% of NFA (rest is lobby, corridors, BOH)
  - room_size: 18–25 sqm for Japanese business hotel
- Revenue = RevPAR × rooms × 365, where RevPAR = occupancy × ADR
- Scenario table: conservative / base / optimistic (vary occupancy + ADR)
- Expense ratio: ~60–65% for limited-service hotels in Japan
  - Labor 27%, OTA 12%, utilities 8%, maintenance 5%, insurance/tax 6%, admin 4%
- Capex reserve: 4% of revenue
- Franchise/brand fee: 5% of revenue (if applicable)

### 3. Conversion Cost Estimation

- Per-tsubo renovation costs (Japan, from raumus.jp data):
  - Light refresh: ¥300K/tsubo
  - Full change-of-use: ¥500K/tsubo
  - With seismic + envelope: ¥800K/tsubo
- Hotel conversion premium: fire safety, plumbing, HVAC → ¥600K–1M/tsubo
- Per-room alternative: ¥8M–18M/room depending on scope
- Adaptive reuse is 20–30% cheaper than new construction

### 4. Total Investment & Return Metrics

```
Total Investment = Acquisition + Transaction Costs (6%) + Conversion
NOI Yield = NOI / Total Investment
Compare yield to market cap rates for the asset class
Simple Payback = Total Investment / NOI
```

### 5. Sensitivity & Break-Even

- Full sensitivity table: 3 revenue scenarios × 3 conversion cost scenarios
- Break-even analysis: what price/ADR/occupancy achieves market cap rate?
- Alternative use comparison: which use generates more NOI?
- **Key output**: the ADR needed to match the alternative-use NOI

### 6. Key Data Sources for Japan Real Estate

| Source | URL | Data |
|---|---|---|
| Cushman & Wakefield Japan | `cushmanwakefield.com` marketbeat PDFs | Transaction comparables, cap rates |
| CBRE Japan | `cbre.co.jp/en/insights/` | Cap rate surveys, office/hotel market |
| Savills Japan | `savills.co.jp/research_articles/` | Hospitality spotlight, office, residential |
| JLL Japan | `jll.com/en-jp/insights/` | Market dynamics, hotel investment |
| Turner & Townsend | `turnerandtownsend.com/insights/` | Construction cost inflation |
| OpenGov.jp | `opengov.jp/en/economy/tourism/` | Accommodation statistics by prefecture |
| JNTO | `statistics.jnto.go.jp/en/` | Visitor arrival statistics |
| Nippon.com | `nippon.com/en/japan-data/` | Annual tourism records |
| Tokyo Metro land prices | `realestate-tokyo.com/news/` | Standard land prices by ward |

## Pitfalls

- **Using CBD office rents for non-CBD locations** — Koto-ku mid-tier
  office rent is ¥20K–30K/tsubo, not ¥70K–100K (Marunouchi/Otemachi)
- **Overestimating hotel ADR** — budget hotels near Toyocho charge ¥8K–12K,
  not ¥20K+. Check existing hotel rates on Tripadvisor/Booking.com
- **Underestimating conversion costs** — Fire Service Act upgrades
  (alarms, emergency lighting, flame-retardant materials) are mandatory
  for lodging and often unbudgeted
- **Ignoring alternative use income** — Always model the as-is use case
  (office) as a baseline. If office NOI > hotel NOI, conversion destroys
  value at that acquisition price
- **NFA vs GFA confusion** — Room count should be based on NFA (usable
  area), not GFA. Price per tsubo should use GFA for comparability with
  transaction data (which reports GFA)