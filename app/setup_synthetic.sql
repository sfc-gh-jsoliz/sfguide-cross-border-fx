-- ============================================================================
-- Cross-Border & FX — setup_synthetic.sql  (TRY mode: no listing needed)
-- ----------------------------------------------------------------------------
-- Cross-Border & FX analytics for a payments processor / merchant acquirer
-- FX & treasury team.
-- Tracks cross-border settlement volume by corridor (origin→dest country /
-- currency pair) against a synthetic FX-rate series, and quantifies FX
-- margin (bps) and FX PnL by corridor and month.
--
-- FULLY SYNTHETIC in BOTH modes: there is NO free FX / exchange-rate series in
-- this account, so CrossBorderFX ships synthetic. Real FX rates are available
-- as a PAID Snowflake Marketplace add-on (e.g. Cybersyn FX / exchange-rate
-- listings); see CROSS_BORDER_DATA_SOURCE_INFO and the README for the upgrade
-- path. setup.sql is identical data (still synthetic) with a note describing
-- how to wire a real paid FX listing in place of CROSS_BORDER_FX_MONTHLY.
--
-- Objects in SNOWPACK_CROSS_BORDER_FX.CORE:
--   CROSS_BORDER_CORRIDOR (dim), CROSS_BORDER_FX_MONTHLY (synthetic FX walk),
--   CROSS_BORDER_VOLUME_MONTHLY (synthetic corridor volume / margin / PnL),
--   CROSS_BORDER_BENCHMARK (wide benchmark view), CROSS_BORDER_SV (semantic view),
--   CROSS_BORDER_REPORTS, CROSS_BORDER_DATA_SOURCE_INFO, CROSS_BORDER_AGENT.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS SNOWPACK_CROSS_BORDER_FX;
CREATE SCHEMA IF NOT EXISTS SNOWPACK_CROSS_BORDER_FX.CORE;
CREATE WAREHOUSE IF NOT EXISTS SNOWPACK_CROSS_BORDER_FX_WH
  WITH WAREHOUSE_SIZE='XSMALL' AUTO_SUSPEND=60 AUTO_RESUME=TRUE INITIALLY_SUSPENDED=TRUE;
USE WAREHOUSE SNOWPACK_CROSS_BORDER_FX_WH;
USE SCHEMA SNOWPACK_CROSS_BORDER_FX.CORE;

-- Type-switch guards (no type differs between modes here, but drop defensively
-- so a prior deploy of a different type cannot block CREATE OR REPLACE).
DROP VIEW  IF EXISTS CROSS_BORDER_BENCHMARK;
DROP VIEW  IF EXISTS CROSS_BORDER_DATA_SOURCE_INFO;
DROP TABLE IF EXISTS CROSS_BORDER_FX_MONTHLY;
DROP TABLE IF EXISTS CROSS_BORDER_VOLUME_MONTHLY;

-- 1. Corridor dimension -------------------------------------------------------
--    One row per settlement corridor; each corridor has a UNIQUE currency pair
--    so joining FX in later is strictly 1:1 (no fan-out).
CREATE OR REPLACE TABLE CROSS_BORDER_CORRIDOR (
  corridor_id STRING, origin_country STRING, dest_country STRING,
  currency_pair STRING, base_fx_rate FLOAT
);
INSERT INTO CROSS_BORDER_CORRIDOR VALUES
  ('COR_USGB','US','GB','USD/GBP',  0.79),
  ('COR_USEU','US','DE','USD/EUR',  0.92),
  ('COR_USMX','US','MX','USD/MXN', 17.20),
  ('COR_USIN','US','IN','USD/INR', 83.10),
  ('COR_USCA','US','CA','USD/CAD',  1.36),
  ('COR_USJP','US','JP','USD/JPY',149.50),
  ('COR_USBR','US','BR','USD/BRL',  5.00),
  ('COR_USAU','US','AU','USD/AUD',  1.52);

-- Per-corridor synthetic drivers (fixed values; growth, margin, FX drift):
--   base_vol_musd  = starting monthly cross-border volume ($M)
--   vol_g          = monthly volume growth
--   base_margin_bps= starting FX margin (bps on volume)
--   fx_drift       = monthly drift applied to the FX rate
CREATE OR REPLACE TEMP TABLE CROSS_BORDER_drivers (
  corridor_id STRING, base_vol_musd FLOAT, vol_g FLOAT, base_margin_bps FLOAT, fx_drift FLOAT
) AS
SELECT * FROM VALUES
  ('COR_USGB', 420, 0.010, 55, -0.0008),
  ('COR_USEU', 610, 0.012, 48, -0.0005),
  ('COR_USMX', 380, 0.018, 72,  0.0015),
  ('COR_USIN', 290, 0.022, 85,  0.0010),
  ('COR_USCA', 350, 0.008, 42,  0.0003),
  ('COR_USJP', 260, 0.006, 60,  0.0020),
  ('COR_USBR', 210, 0.020, 90,  0.0018),
  ('COR_USAU', 180, 0.011, 50,  0.0006)
  AS d(corridor_id, base_vol_musd, vol_g, base_margin_bps, fx_drift);

-- 24 months ending 2026-06-30 (month-end dates). Fixed window → stable re-runs.
CREATE OR REPLACE TEMP TABLE CROSS_BORDER_months AS
SELECT LAST_DAY(DATEADD(month, SEQ4(), '2024-07-01')) AS month_end, SEQ4() AS m_idx
FROM TABLE(GENERATOR(ROWCOUNT => 24));

-- 2. Synthetic FX series by currency pair / month (fixed-seed walk) -----------
CREATE OR REPLACE TABLE CROSS_BORDER_FX_MONTHLY
  COMMENT = 'SYNTHETIC FX rate by currency pair and month (deterministic drift + fixed-seed noise). Replace with a REAL paid Marketplace FX listing to go live.'
AS
SELECT c.currency_pair, m.month_end,
       ROUND(c.base_fx_rate * (1 + d.fx_drift * m.m_idx
             + (UNIFORM(-15, 15, RANDOM(7)) / 1000.0)), 6) AS fx_rate
FROM CROSS_BORDER_CORRIDOR c
JOIN CROSS_BORDER_drivers d USING (corridor_id)
CROSS JOIN CROSS_BORDER_months m;

-- 3. Synthetic corridor volume / margin / PnL --------------------------------
CREATE OR REPLACE TABLE CROSS_BORDER_VOLUME_MONTHLY
  COMMENT = 'SYNTHETIC: this processor''s cross-border settlement volume, FX margin (bps) and FX PnL by corridor and month.'
AS
SELECT v.corridor_id, v.month_end,
       v.cross_border_volume_usd,
       ROUND(v.cross_border_volume_usd / 2500.0, 0)                 AS txn_count,
       ROUND(v.cross_border_volume_usd * f.fx_rate, 0)             AS settled_local_ccy,
       v.fx_margin_bps,
       ROUND(v.cross_border_volume_usd * v.fx_margin_bps / 10000.0, 0) AS fx_pnl_usd
FROM (
  SELECT c.corridor_id, m.month_end,
         ROUND(d.base_vol_musd * 1e6
               * (1 + d.vol_g * m.m_idx)
               * (CASE WHEN MONTH(m.month_end) IN (11,12) THEN 1.08 ELSE 1 END)
               * (1 + UNIFORM(-30, 30, RANDOM(11)) / 1000.0), 0)   AS cross_border_volume_usd,
         ROUND(d.base_margin_bps + UNIFORM(-6, 6, RANDOM(23)), 1)  AS fx_margin_bps
  FROM CROSS_BORDER_CORRIDOR c
  JOIN CROSS_BORDER_drivers d USING (corridor_id)
  CROSS JOIN CROSS_BORDER_months m
) v
JOIN CROSS_BORDER_CORRIDOR c2 ON c2.corridor_id = v.corridor_id
JOIN CROSS_BORDER_FX_MONTHLY f ON f.currency_pair = c2.currency_pair AND f.month_end = v.month_end;

-- 4. Wide benchmark view (single pre-joined grain = corridor_id x month_end) --
--    FX joins 1:1 per (currency_pair, month) → no fan-out. Derived MoM growth
--    is computed here and exposed as an AVG metric in the SV.
CREATE OR REPLACE VIEW CROSS_BORDER_BENCHMARK
  COMMENT = 'Cross-border volume, FX rate, FX margin (bps) and FX PnL by corridor and month, with month-over-month volume growth.'
AS
SELECT v.corridor_id, c.origin_country, c.dest_country, c.currency_pair,
       v.month_end,
       v.cross_border_volume_usd, v.txn_count, v.settled_local_ccy,
       v.fx_margin_bps, v.fx_pnl_usd, f.fx_rate,
       ROUND((v.cross_border_volume_usd
              - LAG(v.cross_border_volume_usd) OVER (PARTITION BY v.corridor_id ORDER BY v.month_end))
             / NULLIF(LAG(v.cross_border_volume_usd) OVER (PARTITION BY v.corridor_id ORDER BY v.month_end), 0)
             * 100, 2) AS vol_mom_growth_pct
FROM CROSS_BORDER_VOLUME_MONTHLY v
JOIN CROSS_BORDER_CORRIDOR c USING (corridor_id)
JOIN CROSS_BORDER_FX_MONTHLY f ON f.currency_pair = c.currency_pair AND f.month_end = v.month_end;

-- 5. Data-source marker (honest: synthetic; real FX is a paid add-on) ---------
CREATE OR REPLACE VIEW CROSS_BORDER_DATA_SOURCE_INFO AS
SELECT 'synthetic' AS mode,
       'Fully synthetic corridor volume AND synthetic FX series (no Marketplace listing required). Real FX / exchange-rate data is NOT free in this account; it is available as a PAID Snowflake Marketplace add-on (e.g. Cybersyn FX listings). To go live, replace CROSS_BORDER_FX_MONTHLY (currency_pair, month_end, fx_rate) with a paid FX view and point CROSS_BORDER_VOLUME_MONTHLY at your settlement data.' AS note;

-- 6. Semantic view (single wide view; composite PK; no RELATIONSHIPS) ---------
CREATE OR REPLACE SEMANTIC VIEW CROSS_BORDER_SV
  TABLES ( cb AS SNOWPACK_CROSS_BORDER_FX.CORE.CROSS_BORDER_BENCHMARK PRIMARY KEY (corridor_id, month_end)
           WITH SYNONYMS = ('cross border','corridors','fx','remittance')
           COMMENT = 'Cross-border settlement volume, FX rate, FX margin and FX PnL by corridor and month' )
  FACTS (
    cb.cross_border_volume_usd AS CROSS_BORDER_VOLUME_USD,
    cb.settled_local_ccy AS SETTLED_LOCAL_CCY,
    cb.txn_count AS TXN_COUNT,
    cb.fx_rate AS FX_RATE,
    cb.fx_margin_bps AS FX_MARGIN_BPS,
    cb.fx_pnl_usd AS FX_PNL_USD,
    cb.vol_mom_growth_pct AS VOL_MOM_GROWTH_PCT
  )
  DIMENSIONS (
    cb.corridor_id AS CORRIDOR_ID WITH SYNONYMS = ('corridor','lane','route') COMMENT = 'Settlement corridor',
    cb.origin_country AS ORIGIN_COUNTRY WITH SYNONYMS = ('source country','from country'),
    cb.dest_country AS DEST_COUNTRY WITH SYNONYMS = ('destination country','to country'),
    cb.currency_pair AS CURRENCY_PAIR WITH SYNONYMS = ('fx pair','ccy pair'),
    cb.month_end AS MONTH_END WITH SYNONYMS = ('month','period','as of'),
    cb.report_year AS YEAR(MONTH_END) WITH SYNONYMS = ('year'),
    cb.report_quarter AS QUARTER(MONTH_END) WITH SYNONYMS = ('quarter')
  )
  METRICS (
    cb.total_cross_border_volume AS SUM(cb.cross_border_volume_usd) COMMENT = 'Total cross-border volume (USD)',
    cb.total_txns AS SUM(cb.txn_count) COMMENT = 'Total cross-border transactions',
    cb.total_fx_pnl AS SUM(cb.fx_pnl_usd) COMMENT = 'Total FX PnL (USD)',
    cb.avg_fx_margin_bps AS AVG(cb.fx_margin_bps) COMMENT = 'Average FX margin in basis points',
    cb.avg_fx_rate AS AVG(cb.fx_rate) COMMENT = 'Average FX rate (non-additive)',
    cb.avg_corridor_growth_pct AS AVG(cb.vol_mom_growth_pct) COMMENT = 'Average month-over-month volume growth (%)'
  )
  COMMENT = 'Cross-border & FX semantic view (synthetic corridor book + synthetic FX series).';

-- 7. Output table + agent -----------------------------------------------------
CREATE TABLE IF NOT EXISTS CROSS_BORDER_REPORTS (
  run_id STRING DEFAULT UUID_STRING(), subject STRING, draft_md STRING, report_md STRING,
  status STRING, edits_applied INT, residual_hedges INT, created_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE AGENT CROSS_BORDER_AGENT
  COMMENT = 'Cross-Border & FX agent (Cortex Analyst over CROSS_BORDER_SV)'
  PROFILE = '{"display_name": "Cross-Border FX Agent", "color": "blue"}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto
  instructions:
    response: 'You are a cross-border payments analyst. Use ONLY figures from the Analyst tool. fx_margin_bps is basis points (100 bps = 1%). Express USD in $B/$M. FX rates are SYNTHETIC here; real FX is a paid Marketplace add-on. Never invent numbers. Be concise and cite the corridor and month.'
    orchestration: 'For any corridor, volume, FX rate, FX margin, or PnL question use the CrossBorderFX Analyst tool.'
    sample_questions:
      - question: 'Which corridors generated the most FX PnL in 2026?'
  tools:
    - tool_spec:
        type: cortex_analyst_text_to_sql
        name: CrossBorderFX
        description: 'Cross-border settlement volume, FX rate, FX margin (bps) and FX PnL by corridor and month.'
  tool_resources:
    CrossBorderFX:
      semantic_view: SNOWPACK_CROSS_BORDER_FX.CORE.CROSS_BORDER_SV
  $$;
