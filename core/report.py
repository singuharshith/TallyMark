"""Export a business analysis report as Markdown or standalone HTML."""
from __future__ import annotations

import time

import markdown as md
import plotly.graph_objects as go


def build_markdown(overviews: dict, qualities: dict, history: list, summary: dict | None = None) -> str:
    out = ["# Tallymark - Business Data Report", f"_Generated {time.strftime('%Y-%m-%d %H:%M')}_", ""]
    if summary:
        out += ["## Executive summary", summary.get("summary", ""), ""]
        out += ["### Key findings"] + [f"- {x}" for x in summary.get("key_findings", [])] + [""]
        out += ["### Recommendations"] + [f"- {x}" for x in summary.get("recommendations", [])] + [""]
    for name, ov in overviews.items():
        q = qualities.get(name, {})
        out += [f"## Dataset: {name}", "", "| KPI | Value |", "|---|---|"] + [f"| {k['label']} | {k['value']} |" for k in ov.kpis] + [""]
        out += ["**Computed facts**", ""] + [f"- {f}" for f in ov.facts] + [""]
        if q:
            out += [f"**Data quality:** {q['score']}/100 (completeness {q['completeness']}%, uniqueness {q['uniqueness']}%, validity {q['validity']}%)", ""]
    if history:
        out += ["## Conversation log", ""]
        for h in history:
            out += [f"### Q: {h.question}", h.text, ""]
            if h.insight:
                out += [f"> {h.insight}", ""]
            if h.sql:
                out += ["```sql", h.sql, "```", ""]
    return "\n".join(out)


def build_html(markdown_text: str, figures: list[go.Figure]) -> str:
    body = md.markdown(markdown_text, extensions=["tables", "fenced_code"])
    charts = "".join(f'<div class="chart">{f.to_html(include_plotlyjs="cdn" if i == 0 else False, full_html=False)}</div>'
                     for i, f in enumerate(figures))
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Tallymark Business Data Report</title>
<style>body{{font-family:Inter,Segoe UI,Arial,sans-serif;max-width:1040px;margin:3rem auto;padding:0 1.5rem;color:#292a28;line-height:1.65}}
h1,h2,h3{{letter-spacing:-.025em}}h1{{color:#292a28}}h2{{margin-top:2.5rem;padding-bottom:.5rem;border-bottom:1px solid #e8e4da}}
p,li{{color:#56574f}}table{{width:100%;border-collapse:collapse;margin:1rem 0 2rem}}td,th{{border:1px solid #e5e2d9;padding:9px 12px;text-align:left}}th{{background:#f4f2ec}}
pre{{background:#292a28;color:#f0efe9;padding:14px;border-radius:8px;overflow:auto}}
blockquote{{border-left:3px solid #e8874a;margin-left:0;padding:4px 0 4px 14px;color:#56574f}}
.chart{{margin:1rem 0 2rem}}</style></head>
<body>{body}<h2>Charts</h2>{charts}</body></html>"""
