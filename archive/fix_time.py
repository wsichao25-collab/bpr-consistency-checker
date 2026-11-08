import csv
from datetime import datetime

IN_FILE = "batch_steps.csv"
OUT_FILE = "batch_steps_fixed.csv"

FORMATS = [
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]

def parse_dt(s):
    s = s.strip()
    for fmt in FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

def read_text(path):
    for enc in ("utf-8-sig", "gb18030", "gbk"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return f.read(), enc
        except UnicodeDecodeError:
            continue
    raise RuntimeError("无法识别文件编码，请手动另存为 UTF-8")

text, used_enc = read_text(IN_FILE)
print(f"检测到输入编码：{used_enc}")

reader = csv.DictReader(text.splitlines())
fieldnames = reader.fieldnames
rows = []
bad = []

for i, row in enumerate(reader, start=2):
    for col in ["start_time", "end_time"]:
        v = row.get(col, "").strip()
        if v in ("", "NA"):
            continue
        dt = parse_dt(v)
        if dt is None:
            bad.append((i, col, v))
        else:
            row[col] = dt.strftime("%Y-%m-%d %H:%M")
    rows.append(row)

if bad:
    print("以下时间无法解析，请手动改：")
    for i, col, v in bad:
        print(f"  第{i}行 {col} = {v!r}")
    print("未写文件，先修上面的再跑一次。")
else:
    with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"完成，共 {len(rows)} 行，已输出到 {OUT_FILE}（UTF-8）")