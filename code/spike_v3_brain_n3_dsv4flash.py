#!/usr/bin/env python3
"""
ToolAbstain · DS-V4-Flash N=3 verification

The 2026-05-08 brain-prompt experiment showed DS-V4-Flash dropped 8.3pp under
v3 brain prompt (W2 book-train question only). N=1 — could be noise.
Re-run W2 specifically + other A-class action questions × 3 trials to confirm.
"""
import json, os, time, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

V3_BRAIN_PROMPT = """你是 Lynn，语气自然友好，默认 1-3 句话完成回复。

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

PROV = {
    "name": "DeepSeek-V4-Flash",
    "url": "https://api.deepseek.com/v1/chat/completions",
    "model": "deepseek-v4-flash",
    "key": os.environ["DEEPSEEK_API_KEY"],
    "sleep": 0.6,
}

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

# Same 12 SHOULD_CALL questions
QS = [
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


def call(prompt, with_prompt: bool):
    msgs = []
    if with_prompt:
        msgs.append({"role":"system","content":V3_BRAIN_PROMPT})
    msgs.append({"role":"user","content":prompt})
    payload = {"model":PROV["model"],"messages":msgs,"tools":TOOLS,"tool_choice":"auto",
               "max_tokens":500,"temperature":0.3,"stream":False}
    req = urllib.request.Request(PROV["url"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type":"application/json","Authorization":f"Bearer {PROV['key']}"},
        method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.load(r)
        msg = d.get("choices",[{}])[0].get("message",{}) or {}
        tc = msg.get("tool_calls") or []
        return {"tcalls":len(tc),
                "tool_names":[x.get("function",{}).get("name") for x in tc],
                "content":(msg.get("content") or "")[:200],
                "ms":int((time.time()-t0)*1000)}
    except Exception as e:
        return {"error": str(e)[:120]}


def main():
    rows = []
    for trial in range(3):
        for cond_name, with_p in [("naked", False), ("v3_brain", True)]:
            print(f"\n=== trial {trial+1}/3 · {cond_name} ===", flush=True)
            for qid, q in QS:
                r = call(q, with_p)
                rec = {"trial": trial, "condition": cond_name, "qid": qid, **r}
                if "error" in r:
                    rec["score"] = None
                else:
                    rec["score"] = 1 if r["tcalls"] > 0 else 0
                rows.append(rec)
                tag = "🛠" if r.get("tcalls",0)>0 else "📝" if r.get("content") else "❌"
                tn = ",".join(r.get("tool_names",[]) or [])
                err = f" [{r.get('error','')[:50]}]" if "error" in r else ""
                print(f"  {qid:3s} {tag} tc={r.get('tcalls','?')} [{tn}]{err}", flush=True)
                time.sleep(PROV["sleep"])

    # Aggregate per question
    print(f"\n\n{'='*80}\nDS-V4-Flash N=3 brain-prompt regression check\n{'='*80}", flush=True)
    print(f"{'qid':<5} | {'naked 0/1/2/total':<22} | {'brain 0/1/2/total':<22} | {'delta':<10}", flush=True)
    print("-"*80, flush=True)
    for qid, q in QS:
        n_runs = [r for r in rows if r["qid"]==qid and r["condition"]=="naked" and r["score"] is not None]
        b_runs = [r for r in rows if r["qid"]==qid and r["condition"]=="v3_brain" and r["score"] is not None]
        n_pass = sum(r["score"] for r in n_runs)
        b_pass = sum(r["score"] for r in b_runs)
        delta = (b_pass/len(b_runs) - n_pass/len(n_runs))*100 if n_runs and b_runs else 0
        print(f"{qid:<5} | {n_pass}/{len(n_runs)}                  | {b_pass}/{len(b_runs)}                  | {delta:+.0f}pp", flush=True)

    # Aggregate overall
    n_total = [r for r in rows if r["condition"]=="naked" and r["score"] is not None]
    b_total = [r for r in rows if r["condition"]=="v3_brain" and r["score"] is not None]
    n_pass = sum(r["score"] for r in n_total)
    b_pass = sum(r["score"] for r in b_total)
    print(f"\nOverall:  naked = {n_pass}/{len(n_total)} ({n_pass/len(n_total):.1%}) | v3_brain = {b_pass}/{len(b_total)} ({b_pass/len(b_total):.1%})")
    delta = (b_pass/len(b_total) - n_pass/len(n_total))*100
    print(f"Delta:    {delta:+.1f} pp")

    out = Path(__file__).parent / f"v3_brain_n3_dsv4flash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"ts":datetime.now().isoformat(),"raw":rows}, ensure_ascii=False, indent=2))
    print(f"\n💾 saved → {out}", flush=True)


if __name__ == "__main__":
    main()
