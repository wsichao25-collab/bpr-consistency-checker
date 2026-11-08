# -*- coding: utf-8 -*-
"""
GMP 批记录一致性核查引擎
规则即配置：所有检查项读取 validation_rules.yaml，按 type 分发执行。
任何单条数据错误只记录偏差，不中断运行。
"""
import re
import yaml
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict


class Deviation:
    def __init__(self, rule_id, severity, location, description, actual="", expected=""):
        self.rule_id = rule_id
        self.severity = severity
        self.location = location
        self.description = description
        self.actual = str(actual)
        self.expected = str(expected)

    def as_dict(self):
        return self.__dict__


def load_csv(path, required_cols):
    """带编码回退与友好报错的读取"""
    df = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            raise SystemExit(f"[错误] 找不到文件: {path}")
    if df is None:
        raise SystemExit(f"[错误] {path} 编码无法识别，请用 Excel 另存为 'CSV UTF-8'")
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise SystemExit(f"[错误] {path} 缺少列: {missing}，实际表头: {list(df.columns)}")
    return df.fillna("").reset_index(drop=True)


def parse_dt(s, fmt):
    return datetime.strptime(str(s).strip(), fmt)


def parse_range(spec):
    """解析 'a~b' / '≤c' / '≥c' / 'x±y' -> (lo, hi) 或 (None, hi) 或 (lo, None)"""
    s = str(spec).strip().replace(" ", "")
    m = re.fullmatch(r"([\d.]+)~([\d.]+)", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.fullmatch(r"[≤<=]([\d.]+)", s)
    if m:
        return None, float(m.group(1))
    m = re.fullmatch(r"[≥>=]([\d.]+)", s)
    if m:
        return float(m.group(1)), None
    m = re.fullmatch(r"([\d.]+)±([\d.]+)", s)
    if m:
        x, y = float(m.group(1)), float(m.group(2))
        return x - y, x + y
    return None, None


def normalize_spec(v):
    lo, hi = parse_range(v)
    if lo is not None and hi is not None:
        return f"{lo:g}~{hi:g}"
    return str(v).strip()


# ---------------- 规则实现（按 YAML 中的 type 分发） ----------------

def r_enum(rule, df, ctx):
    out = []
    for i, v in df[rule["column"]].items():
        if str(v).strip() not in rule["values"]:
            out.append(Deviation(rule["id"], rule.get("severity", "格式"), f"第{i+2}行",
                                 rule["message"], v, "/".join(rule["values"])))
    return out


def r_regex(rule, df, ctx):
    out = []
    pat = re.compile(rule["pattern"])
    for i, v in df[rule["column"]].items():
        if not pat.fullmatch(str(v).strip()):
            out.append(Deviation(rule["id"], rule.get("severity", "格式"), f"第{i+2}行",
                                 rule["message"], v, rule["pattern"]))
    return out


def r_datetime(rule, df, ctx):
    out = []
    fmt = rule.get("format", ctx["fmt"])
    for i, v in df[rule["column"]].items():
        try:
            parse_dt(v, fmt)
        except ValueError:
            out.append(Deviation(rule["id"], rule.get("severity", "格式"), f"第{i+2}行",
                                 rule["message"], v, fmt))
    return out


def r_cross_field(rule, df, ctx):
    out = []
    if rule["operator"] == ">=":
        fmt = ctx["fmt"]
        for i, row in df.iterrows():
            try:
                if parse_dt(row[rule["right"]], fmt) > parse_dt(row[rule["left"]], fmt):
                    out.append(Deviation(rule["id"], rule.get("severity", "逻辑"), f"第{i+2}行",
                                         rule["message"], f'{row[rule["left"]]} >= {row[rule["right"]]}', "False"))
            except ValueError:
                pass  # 格式问题由 datetime 规则报告
    elif rule["operator"] == "equals_batch_mapping_of":
        bm = ctx["batch_mapping"]
        for i, row in df.iterrows():
            if bm.get(str(row[rule["right"]]).strip()) != str(row[rule["left"]]).strip():
                out.append(Deviation(rule["id"], rule.get("severity", "逻辑"), f"第{i+2}行",
                                     rule["message"], f'{row[rule["right"]]} -> {row[rule["left"]]}',
                                     str(bm.get(row[rule["right"]], "未知"))))
    return out


def r_no_overlap(rule, df, ctx):
    out = []
    fmt = ctx["fmt"]
    groups = defaultdict(list)
    for i, row in df.iterrows():
        try:
            key = tuple(row[c] for c in rule["partition_by"])
            groups[key].append((i + 2, parse_dt(row[rule["start"]], fmt), parse_dt(row[rule["end"]], fmt)))
        except ValueError:
            continue
    for key, items in groups.items():
        items.sort(key=lambda x: x[1])
        for a, b in zip(items, items[1:]):
            if b[1] < a[2]:
                out.append(Deviation(rule["id"], rule.get("severity", "偏差"),
                                     f"第{a[0]}行与第{b[0]}行",
                                     rule["message"] + f"（{'/'.join(key)}）",
                                     f"{b[1]:%m-%d %H:%M} 开始", f"应不早于 {a[2]:%m-%d %H:%M}"))
    return out


def r_continuous_work(rule, df, ctx):
    out = []
    fmt = ctx["fmt"]
    threshold = rule.get("threshold_hours", 8)
    gap_min = rule.get("merge_gap_minutes", 30)
    groups = defaultdict(list)
    for i, row in df.iterrows():
        try:
            groups[row[rule["group_by"]]].append((parse_dt(row["start_time"], fmt),
                                                  parse_dt(row["end_time"], fmt), i + 2))
        except ValueError:
            continue
    for who, items in groups.items():
        items.sort()
        cur_s, cur_e, cur_line = items[0]
        for s, e, line in items[1:]:
            if s <= cur_e + timedelta(minutes=gap_min):
                cur_e = max(cur_e, e)
            else:
                if cur_e - cur_s > timedelta(hours=threshold):
                    out.append(Deviation(rule["id"], rule.get("severity", "偏差"), f"第{cur_line}行起",
                                         rule["message"] + f"（{who}）",
                                         f"连续 {(cur_e-cur_s)}", f"≤ {threshold} 小时"))
                cur_s, cur_e, cur_line = s, e, line
        if cur_e - cur_s > timedelta(hours=threshold):
            out.append(Deviation(rule["id"], rule.get("severity", "偏差"), f"第{cur_line}行起",
                                 rule["message"] + f"（{who}）",
                                 f"连续 {cur_e-cur_s}", f"≤ {threshold} 小时"))
    return out


def r_net_weight(rule, df, ctx):
    out = []
    tol = rule.get("tolerance", 0.05)
    for i, row in df.iterrows():
        try:
            init, fin, net = float(row["initial_kg"]), float(row["final_kg"]), float(row["net_kg"])
            if abs((init - fin) - net) > tol:
                out.append(Deviation(rule["id"], rule.get("severity", "偏差"), f"第{i+2}行",
                                     rule["message"] + f"（{row['material']}）",
                                     f"净重 {net}", f"应为 {init-fin:g}"))
        except ValueError:
            continue  # 非数字行（如 pH 控制）跳过
    return out


def r_value_range(rule, df, ctx):
    out = []
    for i, row in df.iterrows():
        try:
            v = float(row["value"])
        except ValueError:
            out.append(Deviation(rule["id"], rule.get("severity", "格式"), f"第{i+2}行",
                                 rule["message"] + f"（{row['param_name']}）", row["value"], "数字"))
            continue
        lo, hi = parse_range(row["expected_range"])
        if lo is None and hi is None:
            continue
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            out.append(Deviation(rule["id"], rule.get("severity", "偏差"), f"第{i+2}行",
                                 rule["message"] + f"（{row['param_name']}）",
                                 v, row["expected_range"]))
    return out


def r_cleaning_validity(rule, df, ctx):
    out = []
    fmt = ctx["fmt"]
    clean = ctx["dfs"]["equipment_clean.csv"]
    cinfo = {}
    for _, r in clean.iterrows():
        try:
            cinfo[r["equipment_id"].strip()] = (parse_dt(r["clean_end_time"], fmt), int(r["valid_days"]))
        except (ValueError, KeyError):
            continue
    flagged = set()
    for i, row in df.iterrows():
        eq = str(row["equipment_id"]).strip()
        if eq not in cinfo:
            continue
        try:
            start = parse_dt(row["start_time"], fmt)
        except ValueError:
            continue
        clean_end, days = cinfo[eq]
        key = (eq, start.date())
        if start > clean_end + timedelta(days=days) and key not in flagged:
            flagged.add(key)
            out.append(Deviation(rule["id"], rule.get("severity", "偏差"),
                                 f"第{i+2}行（{row['batch_id']} {row['step']}）",
                                 rule["message"] + f"（{eq}）",
                                 f"使用于 {start:%m-%d %H:%M}",
                                 f"清洗效期至 {clean_end + timedelta(days=days):%m-%d %H:%M}"))
    return out


def r_spec_consistency(rule, df, ctx):
    out = []
    groups = defaultdict(dict)  # item -> {doc: normalized}
    for _, row in df.iterrows():
        groups[row["item"].strip()][row["doc_no"].strip()] = normalize_spec(row["specified_value"])
    for item, docs in groups.items():
        if len(set(docs.values())) > 1:
            detail = "；".join(f"{d}: {v}" for d, v in docs.items())
            out.append(Deviation(rule["id"], rule.get("severity", "严重"), "文件间",
                                 rule["message"] + f"（{item}）", detail, "各文件应一致"))
    return out


def r_step_sequence(rule, df, ctx):
    out = []
    fmt = ctx["fmt"]
    groups = defaultdict(list)
    for i, row in df.iterrows():
        try:
            key = tuple(int(p) for p in re.findall(r"\d+", str(row["step"])))
            groups[row["batch_id"]].append((key, parse_dt(row["start_time"], fmt), i + 2,
                                            f'{row["step"]} {row["step_name"]}'))
        except ValueError:
            continue
    for batch, items in groups.items():
        items.sort(key=lambda x: (x[0], x[1]))
        for prev, cur in zip(items, items[1:]):
            if cur[1] < prev[1]:
                out.append(Deviation(rule["id"], rule.get("severity", "偏差"),
                                     f"第{prev[2]}行与第{cur[2]}行（{batch}）",
                                     rule["message"], f"{cur[3]} 开始于 {cur[1]:%m-%d %H:%M}",
                                     f"应不早于上一工序 {prev[3]}（{prev[1]:%m-%d %H:%M}）"))
    return out


DISPATCH = {
    "enum": r_enum, "regex": r_regex, "datetime": r_datetime,
    "cross_field": r_cross_field, "no_overlap": r_no_overlap,
    "continuous_work": r_continuous_work, "net_weight": r_net_weight,
    "value_range": r_value_range, "cleaning_validity": r_cleaning_validity,
    "spec_consistency": r_spec_consistency, "step_sequence": r_step_sequence,
}


def run_all(cfg, data_dir="."):
    dfs = {}
    for fname, spec in cfg["files"].items():
        dfs[fname] = load_csv(f"{data_dir}/{fname}", spec["required_cols"])
    ctx = {"fmt": cfg["datetime_format"], "dfs": dfs,
           "batch_mapping": cfg.get("batch_mapping", {})}
    deviations = []
    for rule in cfg["rules"]:
        fname = rule.get("file", "batch_steps.csv")
        fn = DISPATCH.get(rule["type"])
        if fn is None:
            print(f"[警告] 未知规则类型 {rule['type']}（{rule['id']}），已跳过")
            continue
        try:
            deviations += fn(rule, dfs[fname], ctx)
        except Exception as ex:  # 单条规则崩溃不拖垮整体
            deviations.append(Deviation(rule["id"], "系统", "-",
                                        f"规则执行异常: {ex}", "", ""))
    return deviations
