# -*- coding: utf-8 -*-
import os
import sys
import yaml
from rules_engine import run_all
from report import print_summary, write_html

BASE = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    # 只把非 -- 开头的参数当作数据目录（如: python main.py data）
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data_dir = args[0] if args else "data"
    try:
        with open(os.path.join(BASE, "validation_rules.yaml"), encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        deviations = run_all(cfg, os.path.join(BASE, data_dir))
    except SystemExit as e:
        print(e)
        sys.exit(1)

    if "--llm" in sys.argv:  # python main.py --llm 启用 LLM 解释层
        from llm_explainer import enrich
        print("正在调用大模型生成审核意见...")
        deviations = enrich(deviations)

    print_summary(deviations)
    write_html(deviations, os.path.join(BASE, "reports", "deviations.html"))
