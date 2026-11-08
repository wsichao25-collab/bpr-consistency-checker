# BPR Consistency Checker | GMP 批记录一致性核查工具

将 QA 对生产批记录的人工交叉核对，转化为**可配置规则引擎 + 大模型审核意见草稿**的人机协同工具。规则即配置（YAML），新增检查项无需改代码。

Cross-checking of batch production records (BPR) is manual, slow and error-prone. This tool turns QA review logic into a **configurable rule engine**, outputs a deviation report, and optionally drafts review comments via LLM. Rules are YAML-configured — no code change needed to add checks.

## 背景 Background

在药企车间跟进工艺验证与批记录核对时注意到：批记录、称量记录、设备使用/清洗记录、工艺参数表环环相扣，人工对齐极易漏检——时间冲突、净重不符、参数超限、清洗超效期、BPR 与 SOP 规格矛盾。本工具把这类核查逻辑抽象为 17 条规则，对 5 类结构化记录一键核查。

## 架构 Architecture

```
data/ (5 类脱敏合成 CSV)
   │  batch_steps / batch_materials / batch_params / batch_specs / equipment_clean
   ▼
rules_engine.py   ← validation_rules.yaml（17 条规则，规则即配置）
   ▼                                    ▲
deviations（偏差清单）      llm_explainer.py（可选：Kimi / DeepSeek）
   ▼                                    依据内置 GMP 条款字典生成审核意见草稿
reports/deviations.html（核查报告）
```

## 规则清单 Rules（节选）

| ID | 检查项 | 级别 |
|---|---|---|
| R010 | 同一设备时间段不得重叠 | 偏差 |
| R011 | 同一人员不得双岗（跨设备并行预警） | 偏差 |
| R012 | 连续工时 > 8 小时无轮班 | 偏差 |
| R013 | 净重 = 初始 - 结束重量复算 | 偏差 |
| R014 | 工艺参数阈值（pH / 温度 / 干燥失重） | 偏差 |
| R015 | 设备清洗 7 天有效期覆盖 | 偏差 |
| R016 | 受控文件间规格一致性（BPR vs SOP） | 严重 |
| R017 | 工序编号顺序与时间轴 | 偏差 |

完整 17 条见 `validation_rules.yaml`。示例数据为**合成脱敏数据**（基于真实 GMP 文件结构抽象：公司/批号/人员/设备编号均已替换），检出 16 条偏差，其中包含真实文件分析中发现的典型问题（如 BPR 与 SOP 收率范围矛盾 170-230% vs 195~270%）。

## 快速开始 Quickstart

```bash
pip install pandas pyyaml
python main.py          # 规则引擎 + HTML 报告
python main.py --llm    # 追加 LLM 审核意见（需配置 key）
```

LLM 配置（二选一）：

```bash
# .env 文件（已 gitignore）
MOONSHOT_API_KEY=sk-...        # Kimi（默认，模型 kimi-k3）
# 或 DEEPSEEK_API_KEY=sk-...   # 切换需改 llm_explainer.py 的 BASE_URL/MODEL
```

模型列表可用 `python check_models.py` 查询（key 决定可见模型）。

## 边界与免责 Disclaimer

- **预警 ≠ 偏差**：规则引擎只负责"全部报出来"，并行操作等预警由 QA 人工豁免判定，**最终判定权在人**；
- 定位是 QA 辅助工具（人机协同），非放行依据；正式应用需按 GAMP5/CSA 完成计算机化系统验证；
- 本仓库全部为合成脱敏数据，不含任何真实企业信息。

## Roadmap

- 手写批记录 OCR 结构化（多模态大模型）
- 合规排班优化（OR-tools）
- SOP 条款向量库 RAG（替代内置条款字典）
- 偏差趋势可视化看板
- 规则热更新与审计追踪（对应 GxP 计算机化系统要求）

## License

MIT（数据与条款文本仅作演示用途）
## 演示 Demo
![核查报告](GMP批记录核查报告.png)
