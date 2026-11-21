# Synthetic data

Everything in this pack is synthetic. `data/generate.py` builds it with a fixed seed (`20240701`), so every run writes the same numbers, byte for byte:

```bash
python3 data/generate.py
```

It writes:

| File | Rows | What it holds |
|---|---|---|
| `data/corridors.csv` | 8 | One row per settlement corridor: origin and destination country, currency pair, starting FX rate |
| `data/fx_monthly.csv` | 192 | Synthetic FX rate per currency pair and month-end, Jul 2024 to Jun 2026 |
| `data/volume_monthly.csv` | 192 | Cross-border volume (USD), transactions, settled local-currency amount, FX margin (bps) and FX P&L per corridor and month-end |

The same rows are copied to `app/sample/` (read by the app in Sample mode) and pasted into `sql/setup.sql` between the `GENERATED DATA` markers (loaded in Live mode), so Sample and Live show the same figures.

## How the numbers are made

These are the original pack's drivers and formulas; only the noise source changed (a seeded Python RNG instead of Snowflake `RANDOM()`).

- **Volume:** `base volume × (1 + monthly growth × month index) × 1.08 in November and December × (1 ± up to 3% noise)`.
- **FX margin:** the corridor's base margin ± up to 6 bps each month.
- **FX P&L:** `volume × margin bps / 10,000` (100 bps = 1%).
- **Transactions:** volume ÷ $2,500 average ticket.
- **FX rate:** the pair's starting rate × (1 + monthly drift × month index ± up to 1.5% noise).

| Corridor | Pair | Start volume | Monthly growth | Base margin | Monthly FX drift |
|---|---|---|---|---|---|
| United States → Germany | USD/EUR | $610M | 1.2% | 48 bps | -0.05% |
| United States → United Kingdom | USD/GBP | $420M | 1.0% | 55 bps | -0.08% |
| United States → Mexico | USD/MXN | $380M | 1.8% | 72 bps | +0.15% |
| United States → Canada | USD/CAD | $350M | 0.8% | 42 bps | +0.03% |
| United States → India | USD/INR | $290M | 2.2% | 85 bps | +0.10% |
| United States → Japan | USD/JPY | $260M | 0.6% | 60 bps | +0.20% |
| United States → Brazil | USD/BRL | $210M | 2.0% | 90 bps | +0.18% |
| United States → Australia | USD/AUD | $180M | 1.1% | 50 bps | +0.06% |

## Stories planted in the data

Measured from the generated files; the app should surface each one.

1. **Emerging-market lanes grow fastest.** USD/BRL (+52% monthly volume, Jul 2024 to Jun 2026), USD/INR (+49%) and USD/MXN (+39%) outgrow every other corridor. USD/JPY grows least (+10%).
2. **The biggest lane is not the richest per dollar.** USD/EUR carries the most volume and the most 24-month FX P&L ($84.0M) at under 50 bps, while USD/BRL and USD/INR earn 84-91 bps.
3. **Holiday lift.** Total monthly volume steps up about 8% every November and December, then falls back in January (Dec 2025 $3.56B, Jan 2026 $3.31B).
4. **Thin-margin lane.** USD/CAD runs the lowest margin (base 42 bps) and has the slowest FX P&L growth with USD/JPY (+9% for the last 12 months against the 12 before).
5. **Margin squeeze on USD/MXN.** The seeded noise leaves USD/MXN's 3-month average margin 6 bps below its first three months (73.3 to 67.3 bps) while volume grows 39%, so the app flags it *Margin watch*. It comes from the noise, not a planted driver; the fixed seed keeps it in every run.
6. **Dollar moves.** The synthetic dollar weakens against sterling (USD/GBP -4.3% over the window) and strengthens most against the real and the rupee (USD/BRL +5.0%, USD/INR +4.7%).

Month-to-month margin changes of a few bps are noise by construction (± 6 bps), so the app compares three-month averages, not single months, before it flags a margin move.
