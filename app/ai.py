"""AI calls: the grounded desk note (draft + verify with AI_COMPLETE) and Ask the Desk
(the CROSS_BORDER_AGENT Cortex Agent via DATA_AGENT_RUN).

Sample mode replays responses captured from Live runs (sample/ai.json) after a
4-8 s staged wait, and the UI labels them "Sample AI response".
"""
import json
import random
import time
from pathlib import Path

from data import SCHEMA, session

MODEL = "claude-sonnet-4-5"
AGENT = f"{SCHEMA}.CROSS_BORDER_AGENT"
SAMPLE_AI = Path(__file__).parent / "sample" / "ai.json"

SCOPES = {
    "ALL": "All corridors",
    "COR_USEU": "USD/EUR · Germany", "COR_USGB": "USD/GBP · United Kingdom",
    "COR_USMX": "USD/MXN · Mexico", "COR_USIN": "USD/INR · India",
    "COR_USCA": "USD/CAD · Canada", "COR_USJP": "USD/JPY · Japan",
    "COR_USBR": "USD/BRL · Brazil", "COR_USAU": "USD/AUD · Australia",
}

QUESTIONS = [
    "Which corridors generated the most FX P&L in 2026?",
    "Which corridor grew cross-border volume fastest between July 2024 and June 2026?",
    "What was the average FX margin in bps by currency pair over the last 12 months?",
    "How much did total volume rise in November and December 2025 compared with October 2025?",
]

RULES = (
    "You are a cross-border payments analyst. Write a concise corridor / FX desk note using ONLY the FACTS JSON.\n"
    "DATA RULES: use only numbers in FACTS, copy exactly; fx_margin_bps is basis points (100 bps = 1%); dollars are USD, express $B/$M; "
    "volume/PnL change = latest - earliest per corridor; FX rates are SYNTHETIC; no estimates, no hedging, no outside benchmarks; missing = n/d. "
    "Do not name any real bank, processor or company.\n"
    "OUTPUT markdown starting with '# ', a one-line takeaway, a table "
    "(corridor | currency pair | volume start->now | fx margin bps | fx PnL start->now), 3 bullets, ending with '## Data Coverage'."
)


def sample_ai():
    return json.loads(SAMPLE_AI.read_text()) if SAMPLE_AI.exists() else {"notes": {}, "ask": {}}


def note_steps(scope):
    n = 2 if scope != "ALL" else 16
    return [
        f"Building the fact pack: {n} rows from CROSS_BORDER_BENCHMARK (first and latest month-end)",
        f"Drafting the desk note with AI_COMPLETE ({MODEL}) under the DATA RULES",
        "Fact-checking every number against the fact pack with a second AI_COMPLETE pass",
        "Saving the note and verdict to CROSS_BORDER_REPORTS",
    ]


ASK_STEPS = [
    "Sending the question to the Cross-Border FX Agent (DATA_AGENT_RUN)",
    "Cortex Analyst writes SQL over the CROSS_BORDER_SV semantic view",
    "Running the SQL on SNOWPACK_CROSS_BORDER_FX_WH",
    "Composing the answer from the result set",
]


def sample_wait(on_step, steps):
    """Spread a 4-8 s jittered wait over the staged steps (Sample mode only)."""
    total = random.uniform(4.0, 8.0)
    for i, s in enumerate(steps):
        on_step(i, s)
        time.sleep(total / len(steps))


# ---------------------------------------------------------------- desk note (Live)
def fact_pack(scope):
    where = "" if scope == "ALL" else "AND s.corridor_id = ?"
    params = [] if scope == "ALL" else [scope]
    raw = session().sql(f"""
        WITH w AS (SELECT MIN(month_end) a, MAX(month_end) z FROM {SCHEMA}.CROSS_BORDER_BENCHMARK)
        SELECT ARRAY_AGG(OBJECT_CONSTRUCT(
          'corridor', s.corridor_id, 'corridor_name', s.corridor_name, 'currency_pair', s.currency_pair,
          'month', s.month_end::string,
          'cross_border_volume_usd', s.cross_border_volume_usd,
          'fx_rate', s.fx_rate, 'fx_margin_bps', s.fx_margin_bps,
          'fx_pnl_usd', s.fx_pnl_usd)) WITHIN GROUP (ORDER BY s.corridor_id, s.month_end)
        FROM {SCHEMA}.CROSS_BORDER_BENCHMARK s JOIN w ON s.month_end IN (w.a, w.z)
        WHERE TRUE {where}
    """, params=params).collect()[0][0]
    return json.loads(raw)


def complete(prompt):
    raw = session().sql("SELECT AI_COMPLETE(?, ?)", params=[MODEL, prompt]).collect()[0][0]
    # The string result can arrive JSON-encoded ("..." with escapes); decode it once.
    if isinstance(raw, str) and raw.startswith('"'):
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    return raw.strip()


def draft_note(fp):
    return complete(RULES + f"\n\nFACTS: {json.dumps(fp)}")


def verify(fp, draft):
    vp = (
        "You are a fact-checker. Compare the DRAFT against the FACTS JSON (only allowed source). Return ONLY a JSON object with keys "
        "status (exactly 'verified' if every number/claim is supported and no hedge words like likely/approximately/around/could, else exactly 'needs_review'), "
        "residual_hedges (int), edits (array of strings, each naming the unsupported or hedged claim). "
        "Rounding a FACTS number to the draft's display units ($B/$M/$K with one or two decimals, whole or one-decimal "
        "percentages, bps to one decimal) counts as supported; flag only wrong numbers, invented claims and hedges.\n\n"
        f"FACTS: {json.dumps(fp)}\n\nDRAFT:\n{draft}"
    )
    raw = complete(vp)
    s, e = raw.find("{"), raw.rfind("}")
    try:
        v = json.loads(raw[s:e + 1])
    except Exception:
        v = {"status": "needs_review", "residual_hedges": None, "edits": ["The verifier output could not be parsed."]}
    v["status"] = "verified" if v.get("status") == "verified" else "needs_review"
    return v


def save_note(scope, draft, v, fp, latency_ms):
    session().sql(
        f"""INSERT INTO {SCHEMA}.CROSS_BORDER_REPORTS
            (subject, draft_md, report_md, status, edits_applied, residual_hedges, edits, fact_pack, model, latency_ms)
            SELECT ?, ?, ?, ?, ?, ?, PARSE_JSON(?), PARSE_JSON(?), ?, ?""",
        params=[SCOPES[scope], draft, draft, v["status"], len(v.get("edits") or []), v.get("residual_hedges"),
                json.dumps(v.get("edits") or []), json.dumps(fp), MODEL, latency_ms],
    ).collect()


def run_note_live(scope, on_step):
    t0 = time.time()
    steps = note_steps(scope)
    on_step(0, steps[0])
    fp = fact_pack(scope)
    on_step(1, steps[1])
    draft = draft_note(fp)
    on_step(2, steps[2])
    v = verify(fp, draft)
    latency = int((time.time() - t0) * 1000)
    on_step(3, steps[3])
    save_note(scope, draft, v, fp, latency)
    return {"scope": scope, "subject": SCOPES[scope], "markdown": draft, "status": v["status"],
            "edits": v.get("edits") or [], "residual_hedges": v.get("residual_hedges"),
            "fact_pack": fp, "model": MODEL, "latency_ms": latency}


# ---------------------------------------------------------------- ask the desk (Live)
def parse_agent(raw):
    """Final answer = text and table blocks after the last tool block; SQL from the tool result."""
    j = json.loads(raw) if isinstance(raw, str) else raw
    content = j.get("content", [])
    last_tool = max([i for i, b in enumerate(content) if b.get("type") in ("tool_use", "tool_result")], default=-1)
    text, table, sql = [], None, None
    for b in content:
        if b.get("type") == "tool_result":
            for c in b["tool_result"].get("content", []):
                if isinstance(c.get("json"), dict) and c["json"].get("sql"):
                    sql = c["json"]["sql"]
    for b in content[last_tool + 1:]:
        if b.get("type") == "text":
            text.append(b["text"])
        elif b.get("type") == "table" and table is None:
            rs = b["table"].get("result_set", {})
            cols = [c["name"] for c in rs.get("resultSetMetaData", {}).get("rowType", [])]
            table = {"columns": cols, "rows": rs.get("data", [])}
    return {"text": "\n\n".join(text).strip(), "sql": sql, "table": table}


def ask_live(question, on_step):
    t0 = time.time()
    on_step(0, ASK_STEPS[0])
    body = json.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": question}]}], "stream": False})
    raw = session().sql("SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(?, ?)", params=[AGENT, body]).collect()[0][0]
    for i in (1, 2, 3):
        on_step(i, ASK_STEPS[i])
    out = parse_agent(raw)
    out.update({"question": question, "latency_ms": int((time.time() - t0) * 1000)})
    return out
