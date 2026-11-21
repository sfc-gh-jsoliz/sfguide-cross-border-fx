"""Corridors: the lane book with filters, sort, status pills and a detail panel."""
import altair as alt
import pandas as pd
import streamlit as st

import brand
import data
from views.common import cap, load, theme

STATUS_STYLE = {"Accelerating": "background-color:#DCEBF6;color:#1D4E77;font-weight:600",
                "Steady": "background-color:#E3ECE8;color:#3F524B;font-weight:600",
                "Margin watch": "background-color:#FBEFD3;color:#7A4F00;font-weight:600"}


@st.dialog("Corridor detail", width="large")
def detail(df, row):
    g = df[df.corridor_id == row.corridor_id].sort_values("month")
    st.markdown(f'<div style="display:flex;gap:.6rem;align-items:center;flex-wrap:wrap"><b style="font-size:1.15rem">{brand.esc(row.corridor)}</b>'
                f'<span class="fv-pill steady">{brand.esc(row.pair)}</span>{brand.pill(row.status)}</div>', unsafe_allow_html=True)
    tiles = [
        brand.kpi("Volume, latest month", brand.esc(brand.usd(row.volume_latest)), brand.delta(row.volume_growth, f"{brand.pct(row.volume_growth, 0)} since {g.month.iloc[0]:%b %Y}")),
        brand.kpi("FX P&L, last 12 months", brand.esc(brand.usd(row.pnl_12m)), brand.delta(row.pnl_growth, f"{brand.pct(row.pnl_growth, 0)} vs prior 12")),
        brand.kpi("Margin, 3-month avg", brand.esc(f"{row.margin_bps_3m:.1f} bps"), brand.delta(row.margin_change_bps, f"{row.margin_change_bps:+.1f} bps vs first 3 months")),
        brand.kpi("FX rate, window", brand.esc(f"{g.fx_rate.iloc[-1]:,.4f}"), brand.delta(row.fx_change, f"{brand.pct(row.fx_change)} {row.pair}")),
    ]
    st.markdown(f'<div class="fv-kpis" style="margin-top:.8rem">{"".join(tiles)}</div>', unsafe_allow_html=True)
    base = alt.Chart(g).encode(x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0, tickCount=6)))
    tip = [alt.Tooltip("month:T", title="Month-end", format="%B %Y"),
           alt.Tooltip("cross_border_volume_usd:Q", title="Volume (USD)", format="$,.0f"),
           alt.Tooltip("fx_margin_bps:Q", title="Margin (bps)", format=".1f"),
           alt.Tooltip("fx_pnl_usd:Q", title="FX P&L (USD)", format="$,.0f"),
           alt.Tooltip("fx_rate:Q", title="FX rate", format=",.4f")]
    bars = base.mark_bar(color=brand.T["pine500"], opacity=.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        y=alt.Y("fx_pnl_usd:Q", title="FX P&L (USD)", axis=alt.Axis(format="$~s")), tooltip=tip)
    line = base.mark_line(color=brand.T["saffronInk"], strokeWidth=2, point=alt.OverlayMarkDef(size=18)).encode(
        y=alt.Y("fx_margin_bps:Q", title="Margin (bps)", scale=alt.Scale(zero=False)), tooltip=tip)
    st.markdown('<p class="fv-card-h">FX P&amp;L (bars) and margin in bps (line)</p>', unsafe_allow_html=True)
    st.altair_chart(alt.layer(bars, line).resolve_scale(y="independent").properties(height=230), use_container_width=True, theme=None)
    fx = base.mark_line(color=brand.T["fx"], strokeWidth=2).encode(
        y=alt.Y("fx_rate:Q", title=f"{row.pair} rate", scale=alt.Scale(zero=False)), tooltip=tip).properties(height=150)
    st.markdown(f'<p class="fv-card-h">{brand.esc(row.pair)} month-end rate (synthetic)</p>', unsafe_allow_html=True)
    st.altair_chart(fx, use_container_width=True, theme=None)
    t = g[["month_end", "cross_border_volume_usd", "txn_count", "fx_margin_bps", "fx_pnl_usd", "fx_rate", "vol_mom_growth_pct"]].iloc[::-1]
    st.dataframe(t, hide_index=True, use_container_width=True, height=240, column_config={
        "month_end": "Month-end",
        "cross_border_volume_usd": st.column_config.NumberColumn("Volume", format="$%,.0f"),
        "txn_count": st.column_config.NumberColumn("Txns", format="%,.0f"),
        "fx_margin_bps": st.column_config.NumberColumn("Margin bps", format="%.1f"),
        "fx_pnl_usd": st.column_config.NumberColumn("FX P&L", format="$%,.0f"),
        "fx_rate": st.column_config.NumberColumn("FX rate", format="%.4f"),
        "vol_mom_growth_pct": st.column_config.NumberColumn("MoM vol %", format="%+.2f%%"),
    })
    st.markdown(f'<div class="fv-src">Source: <code>CROSS_BORDER_BENCHMARK</code> where corridor_id = <code>{brand.esc(row.corridor_id)}</code> · {len(g)} month-ends</div>', unsafe_allow_html=True)


def render(mode):
    theme()
    df = load(mode)
    summ = data.corridor_summary(df)
    st.markdown(brand.header("Corridors", "Every lane in the book. Filter, sort any column, and select a row to open its detail.",
                             cap(mode, "CROSS_BORDER_BENCHMARK view"), mode != "Live"), unsafe_allow_html=True)
    with st.container(key="card_filters"):
        f1, f2, f3 = st.columns([2, 2, 1.4])
        q = f1.text_input("Search corridor or pair", placeholder="e.g. INR or Brazil")
        statuses = f2.multiselect("Status", ["Accelerating", "Steady", "Margin watch"], placeholder="All statuses")
        min_bps = f3.slider("Min margin (bps)", 0, 100, 0, 5)
    view = summ.copy()
    if q:
        ql = q.lower()
        view = view[view.corridor.str.lower().str.contains(ql) | view.pair.str.lower().str.contains(ql)]
    if statuses:
        view = view[view.status.isin(statuses)]
    view = view[view.margin_bps_3m >= min_bps].reset_index(drop=True)

    if view.empty:
        st.markdown('<div class="fv-card fv-empty"><b>No corridors match these filters</b>Clear the search or lower the margin floor.</div>', unsafe_allow_html=True)
        return

    show = pd.DataFrame({
        "Corridor": view.corridor, "Pair": view.pair, "Status": view.status,
        "Volume, latest": view.volume_latest, "Volume trend ($M)": view.trend,
        "Vol. growth": view.volume_growth * 100, "Margin 3m (bps)": view.margin_bps_3m,
        "Δ margin (bps)": view.margin_change_bps, "FX P&L 12m": view.pnl_12m, "P&L growth": view.pnl_growth * 100,
    })
    styled = show.style.map(lambda s: STATUS_STYLE.get(s, ""), subset=["Status"]).format({
        "Volume, latest": "${:,.0f}", "Vol. growth": "{:+.0f}%", "Margin 3m (bps)": "{:.1f}",
        "Δ margin (bps)": "{:+.1f}", "FX P&L 12m": "${:,.0f}", "P&L growth": "{:+.0f}%"})
    with st.container(key="card_table"):
        st.markdown(f'<p class="fv-card-h">{len(view)} corridors</p><p class="fv-card-s">Select a row for the detail panel. Click a header to sort.</p>', unsafe_allow_html=True)
        ev = st.dataframe(styled, hide_index=True, use_container_width=True, on_select="rerun", selection_mode="single-row",
                          key="corr_table", column_config={
                              "Volume, latest": st.column_config.NumberColumn(format="$%,.0f"),
                              "Volume trend ($M)": st.column_config.LineChartColumn(width="small"),
                              "Vol. growth": st.column_config.NumberColumn(format="%+.0f%%"),
                              "Margin 3m (bps)": st.column_config.NumberColumn(format="%.1f"),
                              "Δ margin (bps)": st.column_config.NumberColumn(format="%+.1f"),
                              "FX P&L 12m": st.column_config.NumberColumn(format="$%,.0f"),
                              "P&L growth": st.column_config.NumberColumn(format="%+.0f%%"),
                          })
    sel = ev.selection.rows if ev and ev.selection else []
    picked = view.iloc[sel[0]].corridor_id if sel else None
    if picked and picked != st.session_state.get("_opened"):
        st.session_state["_opened"] = picked
        detail(df, view.iloc[sel[0]])
    elif not picked:
        st.session_state["_opened"] = None
    if not picked:
        st.caption("Tip: select any row to open the corridor detail.")
