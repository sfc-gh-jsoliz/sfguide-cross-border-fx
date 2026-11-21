"""FX & Margin: FX paths on one indexed axis, a margin heatmap and growth vs margin."""
import altair as alt
import streamlit as st

import brand
import data
from views.common import cap, load, pair_scale, theme


def render(mode):
    theme()
    df = load(mode).copy()
    st.markdown(brand.header("FX & margin", "How the synthetic dollar moved against each pair, and what the desk earned per dollar settled.",
                             cap(mode, "CROSS_BORDER_BENCHMARK view"), mode != "Live"), unsafe_allow_html=True)
    first = df.sort_values("month").groupby("currency_pair")["fx_rate"].transform("first")
    df["fx_index"] = df.fx_rate / first * 100
    pairs = list(brand.PAIR_COLORS)
    pick = st.multiselect("Currency pairs", pairs, default=pairs, key="fx_pairs")
    d = df[df.currency_pair.isin(pick)]
    if d.empty:
        st.markdown('<div class="fv-card fv-empty"><b>No pairs selected</b>Pick one or more currency pairs above.</div>', unsafe_allow_html=True)
        return

    a, b = st.columns([3, 2], gap="medium")
    with a.container(key="card_fx"):
        st.markdown('<p class="fv-card-h">FX rate, indexed (first month = 100)</p><p class="fv-card-s">Above 100: the dollar buys more of that currency than in July 2024.</p>', unsafe_allow_html=True)
        hover = alt.selection_point(fields=["currency_pair"], bind="legend")
        ch = alt.Chart(d).mark_line(strokeWidth=2).encode(
            x=alt.X("month:T", title=None, axis=alt.Axis(format="%b %y", labelAngle=0, tickCount=8)),
            y=alt.Y("fx_index:Q", title="Index", scale=alt.Scale(zero=False)),
            color=alt.Color("currency_pair:N", title=None, scale=pair_scale()),
            opacity=alt.condition(hover, alt.value(1), alt.value(.18)),
            tooltip=[alt.Tooltip("month:T", title="Month-end", format="%B %Y"), alt.Tooltip("currency_pair:N", title="Pair"),
                     alt.Tooltip("fx_rate:Q", title="Rate", format=",.4f"), alt.Tooltip("fx_index:Q", title="Index", format=".1f")],
        ).add_params(hover).properties(height=300)
        rule = alt.Chart().mark_rule(color=brand.T["line"], strokeDash=[4, 3]).encode(y=alt.datum(100))
        st.altair_chart(alt.layer(rule, ch, data=d), use_container_width=True, theme=None)
    summ = data.corridor_summary(df)
    summ = summ[summ.pair.isin(pick)]
    with b.container(key="card_scatter"):
        st.markdown('<p class="fv-card-h">Growth vs margin</p><p class="fv-card-s">Bubble size: FX P&amp;L, last 12 months.</p>', unsafe_allow_html=True)
        s = summ.assign(growth=summ.volume_growth * 100, pnl_m=summ.pnl_12m / 1e6)
        sc = alt.Chart(s).mark_circle(opacity=.85, stroke="#fff", strokeWidth=1).encode(
            x=alt.X("growth:Q", title="Volume growth since Jul 2024 (%)"),
            y=alt.Y("margin_bps_3m:Q", title="Margin, 3-month avg (bps)", scale=alt.Scale(zero=False)),
            size=alt.Size("pnl_m:Q", legend=None, scale=alt.Scale(range=[120, 1400])),
            color=alt.Color("pair:N", title=None, scale=pair_scale(), legend=None),
            tooltip=[alt.Tooltip("pair:N", title="Pair"), alt.Tooltip("growth:Q", title="Volume growth %", format=".1f"),
                     alt.Tooltip("margin_bps_3m:Q", title="Margin bps", format=".1f"), alt.Tooltip("pnl_m:Q", title="FX P&L 12m ($M)", format=".1f")],
        )
        lab = sc.mark_text(dy=-14, fontSize=10, color=brand.T["ink2"]).encode(text="pair:N", size=alt.value(10))
        st.altair_chart(alt.layer(sc, lab).properties(height=300), use_container_width=True, theme=None)

    with st.container(key="card_heat"):
        st.markdown('<p class="fv-card-h">FX margin by month (bps)</p><p class="fv-card-s">Darker is richer. Single-month moves of a few bps are noise; compare 3-month averages on Corridors.</p>', unsafe_allow_html=True)
        hm = alt.Chart(d).mark_rect(cornerRadius=2).encode(
            x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b %y", labelAngle=-45, labelFontSize=10)),
            y=alt.Y("currency_pair:N", title=None, sort=pairs),
            color=alt.Color("fx_margin_bps:Q", title="bps", scale=alt.Scale(range=["#EAF3EF", "#0B2E28"])),
            tooltip=[alt.Tooltip("month:T", title="Month-end", format="%B %Y"), alt.Tooltip("currency_pair:N", title="Pair"),
                     alt.Tooltip("fx_margin_bps:Q", title="Margin (bps)", format=".1f"), alt.Tooltip("fx_pnl_usd:Q", title="FX P&L", format="$,.0f")],
        ).properties(height=260)
        st.altair_chart(hm, use_container_width=True, theme=None)
