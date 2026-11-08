# -*- coding: utf-8 -*-
import os, json, urllib.request, urllib.error

if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

key = os.environ.get("MOONSHOT_API_KEY", "")
req = urllib.request.Request("https://api.moonshot.cn/v1/models",
                             headers={"Authorization": f"Bearer {key}"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    print("你的 key 可用的模型：")
    for m in data.get("data", []):
        print(" -", m.get("id"))
except urllib.error.HTTPError as e:
    print("请求失败:", e.code, e.read().decode("utf-8", errors="replace")[:300])