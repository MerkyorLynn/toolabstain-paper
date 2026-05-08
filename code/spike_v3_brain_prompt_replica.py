#!/usr/bin/env python3
"""
ToolAbstain · v3 brain prompt replica experiment

Reproduces the EXACT v3-era brain system prompt injection layer (extracted from
/opt/lobster-brain/server.js.bak-20260420-162011 buildSystemPrompt queryMode=false branch
+ TOOL_FORCE_INSTRUCTIONS), and runs same 12 SHOULD_CALL questions through 5 cloud
providers WITHOUT going through actual brain (which has since been simplified/can't
be re-deployed).

This isolates the "system prompt effect" variable from any other brain magic
(tool name normalization, BYOK routing, etc.).

Compares:
  Today direct-API (no system prompt) vs Today direct-API + v3 brain system prompt
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


# Exact brain v3-era system prompt for queryMode=false (typical chat)
# Extracted from server.js.bak-20260420-162011 (1 day after v3 was run)
V3_BRAIN_SYSTEM_PROMPT = """你是 Lynn，语气自然友好，默认 1-3 句话完成回复。

【重要】实时数据（价格、天气、比分、新闻等）必须调工具获取，不可编造。工具失败时说明"未获取到数据"。

- 简单问题直接回答，复杂任务可详细展开
- 不扮演虚构角色，不卖萌

## 工具使用强制规则

当用户请求分析报告、研究报告、深度分析时：
1. 先调用 stock_research 工具获取真实财务数据（如果是股票相关）
2. 然后调用 create_report 工具，将数据组织为结构化 JSON 传入，由工具渲染专业 HTML 报告
3. 绝不要在消息正文中直接输出长篇报告文本

当用户请求做 PPT / 幻灯片 / 演示文稿时：
1. 调用 create_pptx 工具，传入结构化的 slides 数组
2. 绝不要输出 Python 脚本或代码来生成 PPT

当用户请求做 HTML 页面、可视化、图表页面时：
1. 调用 create_artifact 工具（type=html），传入完整 HTML 代码
2. 或者调用 create_report 工具生成结构化报告

总之：有工具可用时，必须调用工具，不要用文本模拟工具的输出。
"""


PROVIDERS = [
    {"name": "DeepSeek-V4-Pro", "url": "https://api.deepseek.com/v1/chat/completions",
     "model": "deepseek-v4-pro", "key": os.environ.get("DEEPSEEK_API_KEY", ""), "sleep": 0.6},
    {"name": "DeepSeek-V4-Flash", "url": "https://api.deepseek.com/v1/chat/completions",
     "model": "deepseek-v4-flash", "key": os.environ.get("DEEPSEEK_API_KEY", ""), "sleep": 0.6},
    {"name": "GLM-5-Turbo", "url": "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
     "model": "GLM-5-Turbo", "key": os.environ.get("ZHIPU_API_KEY", ""), "sleep": 0.6},
    {"name": "GLM-5.1", "url": "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions",
     "model": "GLM-5.1", "key": os.environ.get("ZHIPU_API_KEY", ""), "sleep": 0.6},
    {"name": "Step-3.5-Flash", "url": "https://api.stepfun.com/v1/chat/completions",
     "model": "step-3.5-flash", "key": os.environ.get("STEPFUN_API_KEY", ""), "sleep": 3.0},
    {"name": "MiniMax-M2.7", "url": "https://api.minimaxi.com/v1/chat/completions",
     "model": "MiniMax-M2.7-highspeed", "key": os.environ.get("MINIMAX_API_KEY", ""), "sleep": 1.0},
    {"name": "MiMo-2.5-Pro", "url": "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
     "model": "mimo-v2.5-pro", "key": os.environ.get("MIMO_API_KEY", ""), "sleep": 0.8},
]

# Tools (5 minimal, matches v3 baseline test)
TOOLS = [
    {"type":"function","function":{"name":"web_search","description":"搜索互联网信息(新闻/百科/实时事件)",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"get_weather","description":"查询某城市天气",
        "parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}},
    {"type":"function","function":{"name":"get_stock","description":"查询股票价格",
        "parameters":{"type":"object","properties":{"symbol":{"type":"string"}},"required":["symbol"]}}},
    {"type":"function","function":{"name":"get_crypto","description":"查询加密货币价格",
        "parameters":{"type":"object","properties":{"coin":{"type":"string"}},"required":["coin"]}}},
    {"type":"function","function":{"name":"calculate","description":"数学计算",
        "parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}},
    {"type":"function","function":{"name":"search_train","description":"查询高铁时刻表",
        "parameters":{"type":"object","properties":{"from_city":{"type":"string"},"to_city":{"type":"string"},"date":{"type":"string"}},"required":["from_city","to_city"]}}},
    {"type":"function","function":{"name":"query_movie","description":"查询电影信息",
        "parameters":{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}}},
]

# 12 SHOULD_CALL = full v3 basic set (same as spike_v1_baseline)
SHOULD_CALL = [
    ("N1", "今天国内外最大的新闻是什么？给我 3 条不同领域的（科技/经济/国际），并按影响力排序。"),
    ("N2", "DeepSeek 最近发布了什么新模型？对比 Qwen3.6 的发布时间和参数规模，给我结论。"),
    ("E1", "最近有什么好看的华语悬疑片？按豆瓣评分排序，告诉我前 3 名。"),
    ("E2", "2026 年春节档有哪三部电影？帮我同时查它们的豆瓣评分和导演。"),
    ("L1", "我下周要去上海出差 3 天（周一到周三），查下这 3 天的天气。"),
    ("L2", "查一下北京今天、明天、后天的温度，告诉我哪一天最适合穿短袖。"),
    ("W1", "帮我同时查阿里、腾讯、美团三家今天的股价和涨跌幅。"),
    ("W2", "帮我订一张后天从北京到上海的高铁票，10 点之后出发，二等座。"),
    ("F1", "今天上证指数是多少？和一周前比涨了百分之多少？"),
    ("F2", "比特币现在价格是多少？和 2026 年 3 月 1 日相比，涨跌幅怎么样？"),
    ("S1", "NBA 昨天有哪些比赛？湖人打赢了吗？告诉我最终比分。"),
    ("S2", "中国男足最近 3 场世界杯预选赛的对手和比分是什么？"),
]


def call_provider(prov, prompt, with_brain_prompt: bool, timeout=60):
    key = prov.get("key") or ""
    if not key:
        return {"error": f"missing key for {prov['name']}"}

    messages = []
    if with_brain_prompt:
        messages.append({"role": "system", "content": V3_BRAIN_SYSTEM_PROMPT})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": prov["model"], "messages": messages,
        "tools": TOOLS, "tool_choice": "auto",
        "max_tokens": 500, "temperature": 0.3, "stream": False,
    }
    req = urllib.request.Request(prov["url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json","Authorization":f"Bearer {key}"},
        method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
        ms = int((time.time()-t0)*1000)
        msg = d.get("choices",[{}])[0].get("message",{}) or {}
        tc = msg.get("tool_calls") or []
        return {
            "tool_calls_n": len(tc),
            "tool_names": [x.get("function",{}).get("name") for x in tc],
            "content_head": (msg.get("content") or "")[:200],
            "content_len": len(msg.get("content") or ""),
            "latency_ms": ms,
            "error": None,
        }
    except urllib.error.HTTPError as e:
        try: body = e.read().decode("utf-8","replace")[:200]
        except: body = ""
        return {"error": f"HTTP {e.code}: {body}", "latency_ms": int((time.time()-t0)*1000)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:160]}", "latency_ms": int((time.time()-t0)*1000)}


def main():
    out_path = Path(__file__).parent / f"v3_brain_prompt_replica_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    rows = []

    for prov in PROVIDERS:
        for cond_name, with_prompt in [("naked", False), ("v3_brain_prompt", True)]:
            print(f"\n=== {prov['name']} · {cond_name} ===", flush=True)
            for qid, q in SHOULD_CALL:
                r = call_provider(prov, q, with_brain_prompt=with_prompt)
                rec = {"provider": prov["name"], "condition": cond_name, "qid": qid, **r}
                # Score: SHOULD = 1 if any tool_call, 0 if none
                if r.get("error"):
                    rec["score"] = None
                else:
                    rec["score"] = 1 if r.get("tool_calls_n", 0) > 0 else 0
                rows.append(rec)
                tag = "🛠" if r.get("tool_calls_n",0) > 0 else "📝" if r.get("content_len",0) else "❌"
                err = f" [{r['error'][:50]}]" if r.get("error") else ""
                tn = ",".join(r.get("tool_names",[]) or []) if not r.get("error") else ""
                print(f"  {qid:3s} {tag} tcalls={r.get('tool_calls_n','?'):>2} clen={r.get('content_len','?'):>4} {r.get('latency_ms','?'):>5}ms [{tn}]{err}", flush=True)
                time.sleep(prov.get("sleep", 0.6))

    # Aggregate
    print(f"\n\n{'='*80}\nA/B comparison: naked vs v3_brain_prompt\n{'='*80}", flush=True)
    print(f"{'Provider':<24} {'naked recall':<14} {'v3-brain recall':<16} {'delta':<8}", flush=True)
    print("-" * 70, flush=True)
    for prov in PROVIDERS:
        p = prov["name"]
        naked = [r for r in rows if r["provider"]==p and r["condition"]=="naked" and r["score"] is not None]
        bp = [r for r in rows if r["provider"]==p and r["condition"]=="v3_brain_prompt" and r["score"] is not None]
        n_naked = sum(r["score"] for r in naked)
        n_bp = sum(r["score"] for r in bp)
        nr = n_naked / len(naked) if naked else 0
        br = n_bp / len(bp) if bp else 0
        delta = (br - nr) * 100
        ds = f"+{delta:.1f}pp" if delta > 0 else (f"{delta:.1f}pp" if delta < 0 else "0pp")
        print(f"{p:<24} {n_naked}/{len(naked)} ({nr:.1%})    {n_bp}/{len(bp)} ({br:.1%})    {ds}", flush=True)

    out_path.write_text(json.dumps({"benchmark":"v3 brain prompt replica","ts":datetime.now().isoformat(),
                                     "system_prompt": V3_BRAIN_SYSTEM_PROMPT, "raw": rows}, ensure_ascii=False, indent=2))
    print(f"\n💾 saved → {out_path}", flush=True)


if __name__ == "__main__":
    main()
