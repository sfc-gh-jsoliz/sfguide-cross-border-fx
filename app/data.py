"""Data layer: one function per dataset, Sample (bundled CSVs) or Live (Snowflake).

Live never falls back to Sample: a failed query raises, and the page shows the error.
"""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

SCHEMA = "SNOWPACK_CROSS_BORDER_FX.CORE"
WAREHOUSE = "SNOWPACK_CROSS_BORDER_FX_WH"
ROLE = "CROSS_BORDER_FX_ROLE"
SAMPLE_DIR = Path(__file__).parent / "sample"

LIVE_ENV = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH")


def in_snowflake():
    """True when running as Streamlit in Snowflake (an active session exists)."""
    try:
        from snowflake.snowpark.context import get_active_session
        get_active_session()
        return True
    except Exception:
        return False


def live_configured():
    return in_snowflake() or all(os.environ.get(k) for k in LIVE_ENV)


@st.cache_resource(show_spinner=False)
def session():
    """Snowpark session: the app's own in Snowflake, key-pair auth when run locally."""
    if in_snowflake():
        from snowflake.snowpark.context import get_active_session
        return get_active_session()
    from snowflake.snowpark import Session
    return Session.builder.configs({
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "authenticator": "SNOWFLAKE_JWT",
        "private_key_file": os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
        "role": os.environ.get("SNOWFLAKE_ROLE", ROLE),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", WAREHOUSE),
        "database": "SNOWPACK_CROSS_BORDER_FX",
        "schema": "CORE",
    }).create()


def sql_df(q, params=None):
    df = session().sql(q, params=params or []).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


def _benchmark_from_csv():
    c = pd.read_csv(SAMPLE_DIR / "corridors.csv")
    f = pd.read_csv(SAMPLE_DIR / "fx_monthly.csv")
    v = pd.read_csv(SAMPLE_DIR / "volume_monthly.csv")
    df = v.merge(c, on="corridor_id").merge(f, on=["currency_pair", "month_end"])
    df = df.sort_values(["corridor_id", "month_end"])
    prev = df.groupby("corridor_id")["cross_border_volume_usd"].shift(1)
    df["vol_mom_growth_pct"] = ((df["cross_border_volume_usd"] - prev) / prev * 100).round(2)
    return df


@st.cache_data(show_spinner=False, ttl=600)
def benchmark(mode):
    """Corridor x month benchmark (CROSS_BORDER_BENCHMARK in Live)."""
    if mode == "Live":
        df = sql_df(f"""SELECT corridor_id, corridor_name, origin_country, dest_country, currency_pair,
                               month_end::string AS month_end, cross_border_volume_usd, txn_count,
                               settled_local_ccy, fx_margin_bps, fx_pnl_usd, fx_rate, vol_mom_growth_pct
                        FROM {SCHEMA}.CROSS_BORDER_BENCHMARK ORDER BY corridor_id, month_end""")
        for col in ("cross_border_volume_usd", "txn_count", "settled_local_ccy", "fx_margin_bps",
                    "fx_pnl_usd", "fx_rate", "vol_mom_growth_pct"):
            df[col] = pd.to_numeric(df[col])
    else:
        df = _benchmark_from_csv()
    df["month"] = pd.to_datetime(df["month_end"])
    return df.reset_index(drop=True)


def corridor_summary(df):
    """One row per corridor: latest month, 12-month totals, growth, margin trend and a status."""
    rows = []
    for cid, g in df.sort_values("month").groupby("corridor_id"):
        last12, prev12 = g.tail(12), g.head(len(g) - 12)
        first3, last3 = g.head(3)["fx_margin_bps"].mean(), g.tail(3)["fx_margin_bps"].mean()
        pnl_growth = last12["fx_pnl_usd"].sum() / prev12["fx_pnl_usd"].sum() - 1
        vol_growth = g["cross_border_volume_usd"].iloc[-1] / g["cross_border_volume_usd"].iloc[0] - 1
        if last3 - first3 <= -3:
            status = "Margin watch"
        elif pnl_growth >= 0.15:
            status = "Accelerating"
        else:
            status = "Steady"
        rows.append({
            "corridor_id": cid,
            "corridor": g["corridor_name"].iloc[0],
            "pair": g["currency_pair"].iloc[0],
            "status": status,
            "volume_latest": g["cross_border_volume_usd"].iloc[-1],
            "volume_growth": vol_growth,
            "margin_bps_3m": round(last3, 1),
            "margin_change_bps": round(last3 - first3, 1),
            "pnl_12m": last12["fx_pnl_usd"].sum(),
            "pnl_growth": pnl_growth,
            "fx_change": g["fx_rate"].iloc[-1] / g["fx_rate"].iloc[0] - 1,
            "trend": [round(x / 1e6, 1) for x in g["cross_border_volume_usd"]],
        })
    return pd.DataFrame(rows).sort_values("pnl_12m", ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner=False, ttl=30)
def saved_notes(mode):
    if mode != "Live":
        return None
    return sql_df(f"""SELECT run_id, subject, status, edits_applied, residual_hedges, report_md, edits,
                             fact_pack, model, latency_ms, created_at::string AS created_at
                      FROM {SCHEMA}.CROSS_BORDER_REPORTS ORDER BY created_at DESC LIMIT 24""")
