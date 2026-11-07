"""Render docs/architecture.png with matplotlib. Run: python scripts/make_architecture.py"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "docs" / "architecture.png"
BG, CARD, TXT, SUB = "#191A19", "#292A28", "#F0EFE9", "#AAA99F"
VIOLET, BLUE, GREEN, AMBER = "#E8874A", "#38A99B", "#A4B64B", "#E1B64A"

fig, ax = plt.subplots(figsize=(15, 8.5), facecolor=BG)
ax.set_xlim(0, 15); ax.set_ylim(0, 8.5); ax.axis("off"); ax.set_facecolor(BG)


def box(x, y, w, h, title, sub="", color=VIOLET):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.15", fc=CARD, ec=color, lw=1.8))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), title, color=TXT, ha="center", va="center", fontsize=11, fontweight="bold")
    if sub:
        ax.text(x + w / 2, y + h * 0.28, sub, color=SUB, ha="center", va="center", fontsize=8.5)


def arrow(x1, y1, x2, y2, label="", color=SUB):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", color=color, lw=1.6))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.18, label, color=SUB, fontsize=8, ha="center")


ax.text(7.5, 8.05, "Tallymark - Application Architecture", color=TXT, ha="center", fontsize=18, fontweight="bold")
ax.text(7.5, 7.7, "Streamlit web application · Python analysis engine · DuckDB query execution", color=SUB, ha="center", fontsize=10)

box(0.4, 5.6, 2.6, 1.2, "User", "uploads CSVs · asks questions", BLUE)
box(3.6, 5.6, 3.0, 1.2, "Streamlit website", "Overview · Analysis · Data quality\nSQL workspace · Reports", BLUE)
box(7.2, 5.6, 3.0, 1.2, "Loader + Profiler", "encoding/delimiter sniffing\ntype coercion · quality score", GREEN)
box(10.8, 5.6, 3.8, 1.2, "Session state", "tables · conversation history\nlast SQL (context)", GREEN)
arrow(3.0, 6.2, 3.6, 6.2); arrow(6.6, 6.2, 7.2, 6.2); arrow(10.2, 6.2, 10.8, 6.2)

ax.text(0.4, 5.05, "Natural-language analysis pipeline (core/agent.py)", color=AMBER, ha="left", fontsize=11, fontweight="bold")
box(0.4, 3.2, 2.5, 1.4, "1 · Planner", "Groq LLM → JSON\nintent · SQL · chart · reasoning", VIOLET)
box(3.2, 3.2, 2.5, 1.4, "2 · SQL Guard", "single SELECT only\nknown tables · sqlglot AST", AMBER)
box(6.0, 3.2, 2.5, 1.4, "3 · DuckDB Executor", "sandboxed · no file/network\n20s timeout", GREEN)
box(8.8, 3.2, 2.5, 1.4, "4 · Narrator", "Groq LLM sees REAL rows\nanswer · insight · follow-ups", VIOLET)
box(11.6, 3.2, 3.0, 1.4, "5 · Verifier", "figures in text matched\nagainst result table", AMBER)
for a, b in [(2.9, 3.2), (5.7, 6.0), (8.5, 8.8), (11.3, 11.6)]:
    arrow(a, 3.9, b, 3.9)
ax.annotate("", xy=(1.65, 3.2), xytext=(7.25, 3.2), arrowprops=dict(arrowstyle="-|>", color="#D77A68", lw=1.4, connectionstyle="arc3,rad=-0.28"))
ax.text(8.2, 2.6, "SQL error → returned to planner → automatic repair (≤2 retries)", color="#D77A68", fontsize=8.5, ha="left")

box(0.4, 0.4, 3.3, 1.3, "Anomaly Engine", "z-score · IQR · Isolation Forest\nper-row human-readable reasons", GREEN)
box(4.1, 0.4, 3.3, 1.3, "Chart Engine", "Plotly · bar/line/pie/scatter/hist\nspec validation + auto fallback", BLUE)
box(7.8, 0.4, 3.0, 1.3, "Insights + Reports", "KPIs · trends · MD/HTML export", BLUE)
box(11.2, 0.4, 3.4, 1.3, "Observability", "logs/tallymark_activity.jsonl\nlatency · retries · errors", GREEN)
ax.plot([0.4, 14.6], [2.15, 2.15], color="#334155", lw=1, ls="--")
ax.text(14.6, 2.28, "Deterministic engines - work without an LLM", color=SUB, ha="right", fontsize=9)
arrow(8.7, 5.6, 8.7, 4.6, color="#334155")
plt.savefig(OUT, dpi=140, bbox_inches="tight", facecolor=BG)
print("saved", OUT)
