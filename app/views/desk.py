"""Desk: the month-end overview for the FX desk."""
import altair as alt
import streamlit as st

import brand
import data
from views.common import cap, load, pair_scale, theme


def render(mode):
    theme()
    df = load(mode)
    months = sorted(df["month"].unique())
    last, yago, prev = months[-1], months[-13], months[-2]
    m = df.groupby("month").agg(vol=("cross_border_volume_usd", "sum"), pnl=("fx_pnl_usd", "sum"),
                                txn=("txn_count", "sum")).reset_index()
    m["bps"] = m["pnl"] / m["vol"] * 10000
    cur, ya = m[m.month == last].iloc[0], m[m.month == yago].iloc[0]
    trail = m.tail(12)

    st.markdown(brand.header(
        "Corridor desk", f"Month-end {last:%B %Y} across 8 USD settlement corridors. Every figure comes from CROSS_BORDER_BENCHMARK.",
        cap(mode, "CROSS_BORDER_BENCHMARK view"), mode != "Live"), unsafe_allow_html=True)

    vol_b = cur.vol / 1e9
    pnl_m = cur.pnl / 1e6
    tiles = [
        brand.kpi("Cross-border volume, month", brand.counter("$", int(vol_b), f"{vol_b % 1:.2f}B"[1:]),
                  brand.delta(cur.vol / ya.vol - 1, f"{(cur.vol / ya.vol - 1) * 100:.1f}% vs {yago:%b %Y}"),
                  list(trail.vol)),
        brand.kpi("FX P&L, month", brand.counter("$", int(pnl_m), f"{pnl_m % 1:.1f}M"[1:]),
                  brand.delta(cur.pnl / ya.pnl - 1, f"{(cur.pnl / ya.pnl - 1) * 100:.1f}% vs {yago:%b %Y}"),
                  list(trail.pnl)),
        brand.kpi("Blended FX margin", brand.counter("", int(cur.bps), f"{cur.bps % 1:.1f} bps"[1:]),
                  brand.delta(cur.bps - ya.bps, f"{cur.bps - ya.bps:+.1f} bps vs {yago:%b %Y}"), list(trail.bps)),
        brand.kpi("Transactions, month", brand.counter("", int(cur.txn / 1e6), f"{cur.txn / 1e6 % 1:.2f}M"[1:]),
                  brand.delta(cur.txn / ya.txn - 1, f"{(cur.txn / ya.txn - 1) * 100:.1f}% vs {yago:%b %Y}"),
                  list(trail.txn)),
    ]
    st.markdown(f'<div class="fv-kpis">{"".join(tiles)}</div>', unsafe_allow_html=True)

    summ = data.corridor_summary(df)
    fastest = summ.sort_values("volume_growth", ascending=False).iloc[0]
    dec = m[m.month.dt.month == 12].iloc[-1]
    oct_ = m[(m.month.dt.month == 10) & (m.month.dt.year == dec.month.year)].iloc[0]
    st.markdown(
        f'<div class="fv-insight"><b>On the desk this month.</b> {brand.esc(fastest.pair)} is the fastest-growing lane '
        f'({brand.pct(fastest.volume_growth, 0)} monthly volume since {months[0]:%b %Y}). '
        f'Holiday lift: total volume rose {brand.pct(dec.vol / oct_.vol - 1, 1)} from October to December {dec.month:%Y}, '
        f'then fell back in January. Open <b>Corridors</b> for any lane, or <b>Desk Notes</b> for a verified write-up.</div>',
        unsafe_allow_html=True)

    left, right = st.columns([2, 1], gap="medium")
    with left.container(key="card_vol"):
        st.markdown('<p class="fv-card-h">Monthly volume by corridor</p><p class="fv-card-s">Stacked, USD billions. Hover for a corridor and month.</p>', unsafe_allow_html=True)
        d = df.assign(vol_b=df.cross_border_volume_usd / 1e9)
        chart = alt.Chart(d).mark_area(opacity=.85, interpolate="monotone").encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0, tickCount=8)),
            y=alt.Y("sum(vol_b):Q", title="Volume ($B)", stack="zero"),
            color=alt.Color("currency_pair:N", title=None, scale=pair_scale()),
            order=alt.Order("currency_pair:N"),
            tooltip=[alt.Tooltip("month:T", title="Month-end", format="%B %Y"),
                     alt.Tooltip("corridor_name:N", title="Corridor"), alt.Tooltip("currency_pair:N", title="Pair"),
                     alt.Tooltip("vol_b:Q", title="Volume ($B)", format=".3f")],
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True, theme=None)
    with right.container(key="card_rank"):
        st.markdown('<p class="fv-card-h">FX P&amp;L, last 12 months</p><p class="fv-card-s">Ranked by corridor; bar shows share of the leader.</p>', unsafe_allow_html=True)
        top = summ.pnl_12m.max()
        items = "".join(
            f'<li><span class="i">{i + 1:02d}</span><div><div>{brand.esc(r.pair)} <span style="color:var(--muted)">· {brand.esc(r.corridor.split("→")[-1].strip())}</span></div>'
            f'<div class="bar"><i style="width:{r.pnl_12m / top * 100:.0f}%;background:{brand.PAIR_COLORS[r.pair]}"></i></div></div>'
            f'<div style="text-align:right"><div class="n">{brand.usd(r.pnl_12m)}</div>{brand.delta(r.pnl_growth, brand.pct(r.pnl_growth, 0))}</div></li>'
            for i, r in enumerate(summ.itertuples()))
        st.markdown(f'<ul class="fv-rank">{items}</ul>', unsafe_allow_html=True)

    with st.container(key="card_status"):
        st.markdown('<p class="fv-card-h">Corridor status</p><p class="fv-card-s">Margin watch: 3-month average margin down 3 bps or more since the start of the window. Accelerating: otherwise, FX P&amp;L up 15% or more on the prior 12 months.</p>', unsafe_allow_html=True)
        counts = summ.status.value_counts()
        st.markdown(" ".join(f'{brand.pill(s)} <span style="font-family:var(--mono);margin-right:1rem">{counts.get(s, 0)}</span>'
                             for s in ("Accelerating", "Steady", "Margin watch")), unsafe_allow_html=True)
