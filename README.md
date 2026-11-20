# Cross-Border & FX

A grounded, self-verifying cross-border payments analytics example on Snowflake: an app calls Cortex AI_COMPLETE to write a one-page corridor / FX note — settlement volume, FX margin (bps) and FX PnL by corridor — using only a governed semantic view, then a verifier fact-checks the draft and badges it **Verified** or **Needs review**.

Built for a payments processor / merchant acquirer FX & treasury team, on fully synthetic data.

Owner: Javier Soliz · Last reviewed: November 2026

This is not an official Snowflake product.

## What it shows

- A **Streamlit in Snowflake** app with a gallery of corridor / FX notes, each badged Verified / Needs review, and a sidebar that benchmarks every corridor and writes a grounded note.
- A **grounded-generation + verification** loop: a fact pack of allowed numbers → a draft written under strict DATA RULES → a second-pass verifier that flags any unsupported or hedged claim.
- A **Cortex Analyst semantic view** and a **Cortex Agent** over the same corridor book, explorable in Snowsight with natural-language questions.
- Cross-border economics by corridor (origin→destination country / currency pair): `fx_pnl_usd = cross_border_volume_usd × fx_margin_bps / 10000`, with month-over-month volume growth.

## How it works

- The **app** calls Snowflake Cortex `AI_COMPLETE` twice per run — once to draft the note under DATA RULES, once to verify it against the fact pack. The verifier returns a JSON verdict (status, residual hedges, flagged edits) that drives the badge.
- **Setup** also creates a **Cortex Analyst semantic view** (`CROSS_BORDER_SV`) and a **Cortex Agent** (`CROSS_BORDER_AGENT`) over the corridor benchmark. These are explorable in Snowsight (AI & ML → Agents) for natural-language Q&A — they are **not** called by the Streamlit app, which uses `AI_COMPLETE` directly.
- All numbers the model may use come from `CROSS_BORDER_BENCHMARK`, a single wide view at the corridor × month grain, so the FX join is strictly 1:1 with no fan-out.

## Prerequisites

- **Snowflake Enterprise Edition or higher**, in a region where Cortex AISQL and Cortex Agents are available.
- A Snowflake account with Cortex AI functions available in your region (`AI_COMPLETE` defaults to `claude-sonnet-4-5`; change the `MODEL` constant if your account differs).
- A role that can `CREATE DATABASE` and `CREATE WAREHOUSE` (setup provisions a dedicated database and warehouse).
- Streamlit in Snowflake enabled.
- Sample mode is **fully synthetic** and needs no Marketplace purchase. **Real FX / exchange-rate data is not free** — it is a **paid Snowflake Marketplace add-on** (e.g. Cybersyn FX / exchange-rate listings). The pack ships a synthetic FX series so the whole example runs with no purchase; `app/setup.sql` documents the exact swap to a paid FX listing.

## Setup

1. Run [`app/setup_synthetic.sql`](app/setup_synthetic.sql) (TRY) or [`app/setup.sql`](app/setup.sql) (DEPLOY — still synthetic) in a Snowsight worksheet. Both create the dedicated database `SNOWPACK_CROSS_BORDER_FX`, schema `CORE`, and warehouse `SNOWPACK_CROSS_BORDER_FX_WH`, then build all objects. The only difference is the `CROSS_BORDER_DATA_SOURCE_INFO` note describing the paid-FX swap.
2. Create the app **inside `SNOWPACK_CROSS_BORDER_FX.CORE`**: create the stage and the Streamlit app in that schema (upload [`app/streamlit_app.py`](app/streamlit_app.py) to a stage and `CREATE STREAMLIT` over it, or paste it into a new Streamlit in Snowsight). Keeping the stage and app in `SNOWPACK_CROSS_BORDER_FX.CORE` ensures `teardown.sql` removes them with the database. Run it as the owning role.
3. (Optional) Chat with the agent in Snowsight → AI & ML → Agents → **Cross-Border FX Agent**.

## Objects created

| Object | Type | Purpose |
|---|---|---|
| `SNOWPACK_CROSS_BORDER_FX` | Database | Dedicated, isolated database for this pack |
| `SNOWPACK_CROSS_BORDER_FX.CORE` | Schema | Holds all pack objects |
| `SNOWPACK_CROSS_BORDER_FX_WH` | Warehouse | Dedicated XSMALL warehouse (auto-suspend 60s) |
| `CROSS_BORDER_CORRIDOR` | Table | Corridor dimension (origin/dest country, currency pair, base FX rate) |
| `CROSS_BORDER_FX_MONTHLY` | Table | Synthetic FX rate by currency pair and month (swap for a paid FX listing) |
| `CROSS_BORDER_VOLUME_MONTHLY` | Table | Synthetic cross-border volume, FX margin (bps) and FX PnL by corridor and month |
| `CROSS_BORDER_BENCHMARK` | View | Wide corridor × month benchmark with month-over-month volume growth |
| `CROSS_BORDER_DATA_SOURCE_INFO` | View | Data-source marker (synthetic; documents the paid-FX go-live path) |
| `CROSS_BORDER_SV` | Semantic view | Cortex Analyst model over the benchmark (facts, dimensions, metrics) |
| `CROSS_BORDER_REPORTS` | Table | Persisted notes with verifier status, residual hedges and flagged edits |
| `CROSS_BORDER_AGENT` | Cortex Agent | Natural-language agent over `CROSS_BORDER_SV` |
| Streamlit app | Streamlit in Snowflake | The gallery + note-generation UI (`streamlit_app.py`) |

## Cost & time

- Setup runs in a few minutes on the dedicated XSMALL warehouse; data generation is a handful of small `CREATE TABLE AS` statements.
- The app incurs Cortex `AI_COMPLETE` token cost per note run (two calls: draft + verify). Each run is a short note over a small fact pack.
- The warehouse auto-suspends after 60 seconds idle.

## Known limitations

- All data is **synthetic** — corridor volumes and the FX series are generated, not real.
- **Real FX / exchange-rate data is a paid Marketplace add-on**, not included; the pack ships a synthetic FX series so it runs with no purchase.
- The static `try/` landing page uses **mocked AI responses** — illustrative, not live inference.
- This is an illustrative example, not a production application. Review and test before any production use.

## Customize with Cortex Code

Use Cortex Code to adapt this pack to your own corridors and margin economics. Example prompts:

- "Add a USD/NGN and USD/PHP corridor to `CROSS_BORDER_CORRIDOR` and the monthly tables, then regenerate `CROSS_BORDER_BENCHMARK` so the new lanes flow through to the note."
- "Change the FX PnL metric in `CROSS_BORDER_SV` to net margin after a 3 bps hedging cost, and update the DATA RULES in `streamlit_app.py` so the note reflects net margin."
- "Add a verifier rule that flags any corridor note claiming month-over-month volume growth above 40% as needs review."

## Cleanup

Run [`app/teardown.sql`](app/teardown.sql) to drop the dedicated database (and all its objects) and the dedicated warehouse.

## Learn more

- [Snowflake Cortex AISQL (`AI_COMPLETE`)](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql)
- [Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
- [Streamlit in Snowflake](https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit)

## License

Apache 2.0 (see [`LICENSE`](LICENSE)). Illustrative example, as-is, not supported by Snowflake Support. Contains no customer data. Review and test before any production use.
