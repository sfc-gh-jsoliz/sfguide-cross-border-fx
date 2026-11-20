import json
import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Cross-Border & FX", layout="wide")

SCHEMA = "SNOWPACK_CROSS_BORDER_FX.CORE"
MODEL = "claude-sonnet-4-5"
session = get_active_session()
_rerun = getattr(st, "rerun", getattr(st, "experimental_rerun", lambda: None))
BADGE = {"verified": "✅ Verified", "needs_review": "⚠️ Needs review"}


def sql_df(q, p=None):
    df = session.sql(q, params=p or []).to_pandas()
    df.columns = [c.lower() for c in df.columns]
    return df


def data_mode():
    try:
        r = session.sql(f"SELECT mode, note FROM {SCHEMA}.CROSS_BORDER_DATA_SOURCE_INFO").collect()[0]
        return r[0], r[1]
    except Exception:
        return "unknown", ""


def load_reports():
    return sql_df(f"SELECT run_id, subject, status, edits_applied, residual_hedges, report_md, created_at FROM {SCHEMA}.CROSS_BORDER_REPORTS ORDER BY created_at DESC")


def fact_pack():
    return session.sql(f"""
        WITH w AS (SELECT MIN(month_end) a, MAX(month_end) z FROM {SCHEMA}.CROSS_BORDER_BENCHMARK)
        SELECT ARRAY_AGG(OBJECT_CONSTRUCT(
          'corridor', s.corridor_id, 'currency_pair', s.currency_pair,
          'month', s.month_end::string,
          'cross_border_volume_usd', s.cross_border_volume_usd,
          'fx_rate', s.fx_rate, 'fx_margin_bps', s.fx_margin_bps,
          'fx_pnl_usd', s.fx_pnl_usd))
        FROM {SCHEMA}.CROSS_BORDER_BENCHMARK s JOIN w ON s.month_end IN (w.a, w.z)
    """).collect()[0][0]


def draft_note(fp):
    rules = (
        "You are a cross-border payments analyst. Write a concise corridor / FX note using ONLY the FACTS JSON.\n"
        "DATA RULES: use only numbers in FACTS, copy exactly; fx_margin_bps is basis points (100 bps = 1%); dollars are USD, express $B/$M; "
        "volume/PnL change = latest - earliest per corridor; FX rates are SYNTHETIC (real FX is a paid add-on); no estimates, no hedging, no outside benchmarks; missing = n/d.\n"
        "OUTPUT markdown starting with '# ', a one-line takeaway (corridors grew volume / FX PnL), a table "
        "(corridor | currency pair | volume start->now | fx margin bps | fx PnL start->now), 3 bullets, ending with '## Data Coverage'."
    )
    return session.sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, rules + f"\n\nFACTS: {fp}"]).collect()[0][0]


def verify(fp, draft):
    vp = (
        "You are a fact-checker. Compare the DRAFT against the FACTS JSON (only allowed source). Return ONLY a JSON object with keys "
        "status ('verified' if every number/claim is supported and no hedge words like likely/approximately/around/could, else 'needs_review'), "
        "residual_hedges (int), edits (array of strings).\n\n" + f"FACTS: {fp}\n\nDRAFT:\n{draft}"
    )
    raw = session.sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, vp]).collect()[0][0]
    s, e = raw.find("{"), raw.rfind("}")
    try:
        return json.loads(raw[s:e + 1])
    except Exception:
        return {"status": "needs_review", "residual_hedges": None, "edits": ["unparseable verifier output"]}


st.title("Cross-Border & FX")
st.caption("A payments processor's cross-border settlement volume, FX margin (bps) and FX PnL by corridor.")
_mode, _note = data_mode()
if _mode == "synthetic":
    st.warning("Sample mode — synthetic corridor book AND synthetic FX. " + _note)
elif _mode == "marketplace":
    st.info("Live — " + _note)

if "view" not in st.session_state:
    st.session_state["view"] = "gallery"

with st.sidebar:
    st.subheader("Generate a note")
    st.caption("Benchmarks all corridors and writes a verified cross-border / FX note.")
    if st.button("Run cross-border analysis", type="primary", use_container_width=True):
        with st.spinner("Fact pack → grounded draft → verify (~20-40s)..."):
            fp = fact_pack()
            draft = draft_note(fp)
            v = verify(fp, draft)
            status = "verified" if v.get("status") == "verified" else "needs_review"
            session.sql(
                f"INSERT INTO {SCHEMA}.CROSS_BORDER_REPORTS (subject, draft_md, report_md, status, edits_applied, residual_hedges) SELECT ?, ?, ?, ?, ?, ?",
                params=["Cross-border FX performance", draft, draft, status, len(v.get("edits", [])), v.get("residual_hedges")],
            ).collect()
        st.success(f"Done — {BADGE[status]}")
        st.session_state["view"] = "gallery"
        _rerun()

if st.session_state["view"].startswith("report:"):
    run_id = st.session_state["view"].split(":", 1)[1]
    rpt = load_reports()
    row = rpt[rpt["run_id"] == run_id]
    if st.button("← Back to gallery"):
        st.session_state["view"] = "gallery"
        _rerun()
    if not row.empty:
        r = row.iloc[0]
        st.markdown(f"**{BADGE.get(r['status'], r['status'])}**  &nbsp; residual hedges: {r['residual_hedges']}  |  flagged: {r['edits_applied']}")
        st.divider()
        st.markdown(r["report_md"])
else:
    reports = load_reports()
    if reports.empty:
        st.info("No notes yet. Use the sidebar to generate one.")
    else:
        cols = st.columns(3)
        for i, (_, r) in enumerate(reports.iterrows()):
            with cols[i % 3]:
                c = st.container()
                c.markdown(f"**{BADGE.get(r['status'], r['status'])}**")
                c.markdown(f"**{r['subject']}**")
                c.caption(f"{str(r['created_at'])[:16]} · {r['edits_applied']} flagged")
                if c.button("Open report", key=f"open_{r['run_id']}", use_container_width=True):
                    st.session_state["view"] = f"report:{r['run_id']}"
                    _rerun()
                c.markdown("---")
