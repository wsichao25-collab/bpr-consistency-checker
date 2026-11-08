# -*- coding: utf-8 -*-
"""核查报告生成：控制台摘要 + HTML 报告（含 LLM 审核意见）"""
import os
import pandas as pd


def print_summary(deviations):
    print(f"\n核查完成：共发现 {len(deviations)} 条偏差/问题\n")
    for d in deviations:
        print(f"[{d.severity}|{d.rule_id}] {d.location}: {d.description}")
        if d.actual:
            print(f"    实际: {d.actual} | 期望: {d.expected}")


def write_html(deviations, path="reports/deviations.html"):
    rows = []
    for d in deviations:
        row = d.as_dict()
        row["explanation"] = getattr(d, "explanation", "")
        rows.append(row)
    df = pd.DataFrame(rows, columns=["rule_id", "severity", "location", "description",
                                     "actual", "expected", "explanation"])
    sev_order = {"严重": 0, "偏差": 1, "逻辑": 2, "格式": 3, "系统": 4}
    df["_o"] = df["severity"].map(lambda s: sev_order.get(s, 9))
    df = df.sort_values(["_o", "rule_id"]).drop(columns="_o")
    # 控制台同时输出 LLM 意见
    for _, r in df.iterrows():
        if r["explanation"]:
            print(f"\n--- LLM 审核意见 [{r['rule_id']}] ---\n{r['explanation']}")
    html = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>GMP 批记录核查报告</title>
<style>
body{{font-family:'Microsoft YaHei',sans-serif;margin:32px;color:#222}}
h1{{font-size:20px}} h2{{font-size:14px;color:#555}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:12px}}
th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left;vertical-align:top}}
th{{background:#f0f2f5}} .sev-严重{{color:#c0392b;font-weight:bold}}
.sev-偏差{{color:#d35400;font-weight:bold}}
.badge{{display:inline-block;background:#c0392b;color:#fff;border-radius:10px;padding:2px 10px;font-size:12px}}
.exp{{white-space:pre-wrap;color:#34495e}}
</style></head><body>
<h1>GMP 批记录一致性核查报告 <span class="badge">{len(deviations)} 条偏差</span></h1>
<h2>规则引擎定位 + LLM 生成审核意见草稿；预警不等于偏差，最终判定权在 QA。</h2>
{df.to_html(index=False, escape=False, classes="exp")}
</body></html>"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nHTML 报告已生成: {path}")
