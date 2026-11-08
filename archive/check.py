import csv
import re
import yaml
from datetime import datetime
from collections import defaultdict

RULES_FILE = "validation_rules.yaml"
DATA_FILE = "batch_steps.csv"

with open(RULES_FILE, encoding="utf-8") as f:
    rules = yaml.safe_load(f)

fmt = rules["datetime_format"]
batch_map = rules["batch_mapping"]
op_enum = set(rules["operator_enum"])
eq_enum = set(rules["equipment_enum"])
step_pattern = rules["step_pattern"]

errors = []
rows = []

with open(DATA_FILE, encoding="utf-8", newline="") as f:
    reader = csv.DictReader(f)
    expected_cols = [c["name"] for c in rules["columns"]]
    if reader.fieldnames != expected_cols:
        errors.append(f"表头不对，应为：{','.join(expected_cols)}")
    for line_no, row in enumerate(reader, start=2):
        rows.append((line_no, row))

        if row["doc_no"] not in batch_map:
            errors.append(f"第{line_no}行：doc_no 不在枚举中")
        elif batch_map[row["doc_no"]] != row["batch_id"]:
            errors.append(f"第{line_no}行：doc_no 与 batch_id 不匹配")

        if row["operator"] not in op_enum:
            errors.append(f"第{line_no}行：operator 非法")

        if row["equipment_id"] not in eq_enum:
            errors.append(f"第{line_no}行：equipment_id 非法")

        if not re.match(step_pattern, row["step"]):
            errors.append(f"第{line_no}行：step 格式错误")

        try:
            start = datetime.strptime(row["start_time"], fmt)
            end = datetime.strptime(row["end_time"], fmt)
            if end < start:
                errors.append(f"第{line_no}行：end_time 早于 start_time")
        except ValueError:
            errors.append(f"第{line_no}行：时间格式错误")

# 同一设备时间段不得重叠
by_eq = defaultdict(list)
for line_no, row in rows:
    by_eq[(row["doc_no"], row["equipment_id"])].append(
        (line_no, datetime.strptime(row["start_time"], fmt), datetime.strptime(row["end_time"], fmt))
    )

for key, items in by_eq.items():
    items.sort(key=lambda x: x[1])
    for i in range(1, len(items)):
        prev_line, _, prev_end = items[i - 1]
        cur_line, cur_start, _ = items[i]
        if cur_start < prev_end:
            errors.append(f"第{prev_line}行与第{cur_line}行：设备 {key[1]} 时间段重叠")

if errors:
    print("校验失败：")
    for e in errors:
        print(" -", e)
else:
    print(f"校验通过，共 {len(rows)} 行数据")

# 检查通过或失败，都按规则字段打印表头