# -*- coding: utf-8 -*-
"""
LLM 偏差解释层（批量版）：每 5 条偏差合并为 1 次 API 调用，共 4 次
- key 从 .env 或环境变量 MOONSHOT_API_KEY 读取
- 若 404：把 MODEL 改为 kimi-k2-0711-preview
"""
import os
import re
import json
import time
import urllib.request
import urllib.error

if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("MOONSHOT_API_KEY", "")
BASE_URL = "https://api.moonshot.cn/v1/chat/completions"
MODEL = "kimi-k3"                 # 该 key 实测可用模型：kimi-k3 / kimi-k3.1-pro
SLEEP_BETWEEN = 20                # 每次调用间隔（秒）
RETRY_WAIT = 45                   # 429 重试等待（秒）
MAX_RETRY = 3
CHUNK = 5                         # 每次调用处理的偏差条数

CLAUSE = {
    "R010": "SOP·204·3·6201：批生产评价要求'设备、动力、计量器具运转正常'；批记录应真实反映设备使用先后顺序。",
    "R011": "GMP 数据可靠性（ALCOA+）原则：记录应同步、真实；批生产评价要求'操作符合SOP、BPR'，人员不得同时操作两台设备。",
    "R012": "GMP 生产管理要求：操作人员应合理安排班次，避免疲劳操作；批记录应如实记录操作者。",
    "R013": "GMP 物料平衡原则：称量记录应做到'计算者/复核者'双重复核，净重=初始重量-结束重量。",
    "R014": "BPR·204·193·02/03 工艺参数章节：工艺参数（pH、温度、干燥失重）超出规定范围即属偏差，应按偏差管理流程处理。",
    "R015": "SOP·204·3·6201/6202：设备清洗后有效期为7天，过期后须按4.4方法重新清洗后再开工。",
    "R016": "GMP 文件管理要求：受控文件（BPR与SOP）同一规格应保持一致；不一致时应启动文件修订或偏差调查。",
    "R017": "BPR 生产步骤章节：工序应按编号顺序执行，时间轴应与工序顺序一致。",
}

BATCH_PROMPT = """你是药企 QA 审核助手。请对下面 {n} 条核查发现的偏差，逐条输出审核意见。
格式要求（必须严格遵守）：
【编号】
1. 违反条款：一句话，含条款名称
2. 风险：一句话
3. CAPA：一句话

每条总字数不超过 120 字，不要展开解释、不要背景介绍、不要编号列表之外的任何文字。

{items}"""


def _call_api(prompt, timeout=120):
    body = {"model": MODEL,
            "messages": [{"role": "user", "content": prompt}]}
    req = urllib.request.Request(
        BASE_URL, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        return f"__HTTP_{e.code}__:{detail}"
    except Exception as e:
        return f"__ERR__:{e}"


def _build_prompt(chunk):
    items = []
    for local_i, d in enumerate(chunk):
        clause = CLAUSE.get(d.rule_id, "GMP 一般原则与数据可靠性要求（ALCOA+）。")
        items.append(f"编号：{local_i}\n偏差：{d.description}（{d.location}）"
                     f"\n实际值：{d.actual or '-'}；期望值：{d.expected or '-'}"
                     f"\n相关条款：{clause}")
    return BATCH_PROMPT.format(n=len(chunk), items="\n\n".join(items))


def _parse(text, n):
    """按【编号】切分，返回 {local_index: 意见}"""
    out = {}
    parts = re.split(r"[【\[]\s*(\d+)\s*[】\]]", text)
    for i in range(1, len(parts) - 1, 2):
        idx = int(parts[i])
        if 0 <= idx < n:
            out[idx] = parts[i + 1].strip()
    return out


def enrich(deviations):
    if not API_KEY:
        for d in deviations:
            d.explanation = "（未配置 MOONSHOT_API_KEY，跳过 LLM 解释）"
        return deviations
    chunks = [deviations[i:i + CHUNK] for i in range(0, len(deviations), CHUNK)]
    for ci, chunk in enumerate(chunks, 1):
        print(f"  批量解释第 {ci}/{len(chunks)} 批（{len(chunk)} 条偏差）...")
        result = _call_api(_build_prompt(chunk))
        for _ in range(MAX_RETRY):
            if not result.startswith("__HTTP_429"):
                break
            print(f"  触发限流，{RETRY_WAIT}秒后重试...")
            time.sleep(RETRY_WAIT)
            result = _call_api(_build_prompt(chunk))
        if result.startswith("__HTTP_404"):
            print("  [提示] 404：请把 llm_explainer.py 中 MODEL 改为 kimi-k2-0711-preview 后重试")
            for d in chunk:
                d.explanation = "（LLM 调用失败 404，请更换模型名）"
            continue
        if result.startswith("__"):
            for d in chunk:
                d.explanation = f"（LLM 调用失败：{result.strip()}）"
            continue
        parsed = _parse(result, len(chunk))
        for li, d in enumerate(chunk):
            d.explanation = parsed.get(li, "（模型未返回本条意见，可单独重试）")
        if ci < len(chunks):
            time.sleep(SLEEP_BETWEEN)
    return deviations
