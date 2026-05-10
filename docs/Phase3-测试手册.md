# Phase 3 Agent 测试手册

> 2026-05-10 | 验收 Phase 3 LangGraph Agent 的 4 项核心能力

---

## 一、环境确认

```powershell
cd C:\Users\Lenovo\Desktop\Medical-Health-Agent

# 验证所有节点可导入
python -c "from agents.state import AgentState; from agents.boundary import check_emergency; from agents.router import router_node; from agents.analysis import retrieve, generate, reflect, revise; from agents.perception import perception_node; from agents.action import action_node, reject_node; from agents.graph import build_graph, chat; print('ALL IMPORTS OK')"

# 验证 Graph 编译
python -c "from agents.graph import build_graph; g=build_graph(); print(type(g).__name__)"
# → CompiledStateGraph
```

---

## 二、单元测试

### 2.1 硬边界紧急检测

```powershell
python -c "
from agents.boundary import check_emergency

tests = [
    ('我胸痛呼吸困难', True),
    ('小孩发烧39度怎么办', False),
    ('你好', False),
    ('我头疼了一天', False),
    ('我突然意识丧失', True),
    ('心脏病怎么预防', False),
    ('我摔断了腿', True),
    ('吃什么能降血压', False),
]
for q, expected in tests:
    ok, msg = check_emergency(q)
    status = '✅' if ok == expected else '❌'
    print(f'{status} \"{q[:25]}\" → emergency={ok} (expected={expected})')
"
```

**预期**：全部 ✅。

### 2.2 路由准确率

```powershell
python -c "
from agents.router import router_node

tests = [
    ('我今天心率怎么样？', 'health_data', 'perception'),
    ('小孩发烧39度怎么办？', 'medical_qa', 'analysis'),
    ('你好', 'general_chat', 'action'),
    ('高血压怎么预防？', 'medical_qa', 'analysis'),
    ('我昨晚睡眠怎么样？', 'health_data', 'perception'),
    ('今天走了多少步？', 'health_data', 'perception'),
    ('感冒吃什么药？', 'medical_qa', 'analysis'),
    ('谢谢你的建议', 'general_chat', 'action'),
    ('糖尿病饮食需要注意什么？', 'medical_qa', 'analysis'),
    ('我的HRV趋势如何？', 'health_data', 'perception'),
]
correct = 0
for q, exp_intent, exp_route in tests:
    r = router_node({'query': q})
    ok = r['intent'] == exp_intent
    correct += ok
    print(f'{\"✅\" if ok else \"❌\"} \"{q[:30]}\" → {r[\"intent\"]} \"{exp_intent}\"')
print(f'\n准确率: {correct}/{len(tests)} ({correct/len(tests)*100:.0f}%)')
"
```

**预期**：≥8/10 正确。

### 2.3 RAG 检索

```powershell
python -c "
from agents.analysis import _get_retriever, retrieve
from agents.state import AgentState as AS

# 检索
state = {'query': '小孩发烧39度怎么办？'}
r = retrieve(state)
print(f'检索到 {len(r[\"retrieved_docs\"])} 条结果')
for i, d in enumerate(r['retrieved_docs'][:3]):
    print(f'  [{i+1}] score={d[\"score\"]:.3f}  {d[\"content\"][:60]}...')
"
```

**预期**：Top-3 至少 2 条与小儿发热相关。

### 2.4 Self-RAG 反射 JSON 解析

```powershell
python -c "
from agents.analysis import _parse_reflection

tests = [
    ('{\"action\": \"pass\", \"score\": 9, \"issues\": \"\"}', 'pass'),
    ('{\"action\": \"retry\", \"score\": 6, \"issues\": \"缺少引用标注\"}', 'retry'),
    ('{\"action\": \"reject\", \"score\": 3, \"issues\": \"编造了诊断结论\"}', 'reject'),
    ('答案质量很好 {\"action\": \"pass\", \"score\": 8, \"issues\": \"\"} 无需修改', 'pass'),  # 带多余文本
    ('', 'pass'),  # 空输入 → fallback pass
]
for raw, exp_action in tests:
    r = _parse_reflection(raw)
    ok = r['action'] == exp_action
    print(f'{\"✅\" if ok else \"❌\"} {raw[:50]}... → {r[\"action\"]}')
"
```

**预期**：全部 ✅（含异常输入 fallback）。

---

## 三、集成测试

### 3.1 端到端对话（需 FastAPI 运行）

**启动服务**：

```powershell
# 终端1
python -m data_pipeline.webhook_server

# 等待启动完成后，终端2 测试
```

**3.1.1 医疗问答**

```powershell
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/chat',
    json={'query': '小孩发烧39度怎么办？'})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
"
```

**预期**：
- `intent` = `medical_qa`
- `response` 含具体建议和 RAG 引用
- `safety_level` = `normal`

**3.1.2 健康数据查询**

```powershell
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/chat',
    json={'query': '我今天心率怎么样？'})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
"
```

**预期**：
- `intent` = `health_data`
- `response` 含心率均值、偏离基线 sigma 值

**3.1.3 紧急短路**

```powershell
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/chat',
    json={'query': '我胸痛呼吸困难'})
resp = r.json()
print(json.dumps(resp, indent=2, ensure_ascii=False))
"
```

**预期**：
- `safety_level` = `emergency`
- `response` 含 `120` 关键词
- `source` = `rule`（不调 LLM）
- 响应时间 <0.1s（纯规则匹配）

**3.1.4 一般对话**

```powershell
python -c "
import requests, json
r = requests.post('http://localhost:8000/api/v1/chat',
    json={'query': '你好'})
print(json.dumps(r.json(), indent=2, ensure_ascii=False))
"
```

**预期**：
- `intent` = `general_chat`
- `response` 为友好问候

### 3.2 验证 Self-RAG 自检流程

```powershell
python -c "
import requests, json

# 发送一个需要复杂医学知识的问题
r = requests.post('http://localhost:8000/api/v1/chat',
    json={'query': '高血压患者每天应该测量几次血压？需要注意什么？'})
resp = r.json()
print(f'intent: {resp[\"intent\"]}')
print(f'safety_level: {resp[\"safety_level\"]}')
print(f'retry_count: {resp[\"retry_count\"]}')
print(f'response: {resp[\"response\"][:200]}...')
"
```

观察 `retry_count`：
- `0` = Self-RAG 一次通过（正常）
- `1`~`2` = 触发过修正（偶尔）
- 不应出现无限循环（`retry_count` ≤2）

---

## 四、质量评估（20条测试集）

创建 `tests/phase3_quality.py` 或在终端直接执行：

```powershell
# 4.1 路由准确率评估
python -c "
from agents.router import router_node

cases = [
    # (query, intent, route)
    ('我今天心率怎么样？', 'health_data', 'perception'),
    ('小孩发烧39度怎么办', 'medical_qa', 'analysis'),
    ('麻烦帮我看看睡眠数据', 'health_data', 'perception'),
    ('高血压饮食需要注意什么', 'medical_qa', 'analysis'),
    ('新冠疫苗副作用有哪些', 'medical_qa', 'analysis'),
    ('最近一周步数达标了吗', 'health_data', 'perception'),
    ('谢谢', 'general_chat', 'action'),
    ('头疼是什么原因引起的', 'medical_qa', 'analysis'),
    ('我的HRV比基线低', 'health_data', 'perception'),
    ('感冒吃什么药好得快', 'medical_qa', 'analysis'),
    ('什么是BMI', 'medical_qa', 'analysis'),
    ('今天运动量够了吗', 'health_data', 'perception'),
    ('颈椎病怎么缓解', 'medical_qa', 'analysis'),
    ('心情不好怎么办', 'general_chat', 'action'),
    ('躺着心率比平时快正常吗', 'health_data', 'perception'),
    ('糖尿病早期症状', 'medical_qa', 'analysis'),
    ('今天天气不错', 'general_chat', 'action'),
    ('静息心率60算正常吗', 'medical_qa', 'analysis'),
    ('我这周睡眠质量如何', 'health_data', 'perception'),
    ('深呼吸能不能降心率', 'medical_qa', 'analysis'),
]

correct = 0
for q, ei, er in cases:
    r = router_node({'query': q})
    if r['intent'] == ei:
        correct += 1
    else:
        print(f'  ✗ \"{q[:25]}\" → {r[\"intent\"]} (expected {ei})')
print(f'\n路由准确率: {correct}/{len(cases)} ({correct/len(cases)*100:.0f}%)')
"
```

**目标**：≥85%（≥17/20）。

```powershell
# 4.2 RAG 检索评估
python -c "
from agents.analysis import _get_retriever, retrieve
from agents.state import AgentState as AS

questions = [
    '小孩发烧39度怎么办？',
    '高血压患者饮食注意事项',
    '糖尿病的早期症状有哪些',
    '新冠后遗症怎么恢复',
    '颈椎病怎么治疗',
    '失眠怎么改善',
    '胃疼怎么缓解',
    '孕妇感冒能吃药吗',
    '骨折后多久能恢复',
    '抑郁症有什么表现',
]

r = _get_retriever()
hits = 0
for q in questions:
    state = {'query': q}
    result = retrieve(state)
    docs = result['retrieved_docs'][:3]
    top_scores = [d['score'] for d in docs]
    avg = sum(top_scores) / len(top_scores) if top_scores else 0
    print(f'  {q[:30]:30s} | Top3 scores: {top_scores} | avg={avg:.3f}')
    if avg > 0.5:
        hits += 1
print(f'\n高相关比例: {hits}/{len(questions)} (目标是 >= 8/10)')
"
```

**目标**：≥8/10 条问题 Top-3 平均相关度 >0.5。

---

## 五、常见问题

| 现象 | 排查 |
|------|------|
| `ImportError: attempted relative import` | 必须在项目根目录运行 `python -m data_pipeline.webhook_server` |
| `FileNotFoundError: ChromaDB 目录不存在` | 确认 `rag/data/chroma/chroma.sqlite3` 存在 |
| Router 一直回 `general_chat` | 检查 Qwen3-Max API Key（`DASHSCOPE_API_KEY` 环境变量） |
| `/api/v1/chat` 404 | 确认已重启 FastAPI 加载新端点 |
| `retry_count` 总是 2 | 检查 reflect 的 LLM 输出格式，可能 JSON 解析 fallback 触发 |
| 回答含编造内容 | reflect 阈值偏高（≥8），可适当降低到 ≥7 |
| 响应时间超过 30s | 检查网络、Qwen API 限流。Self-RAG 最多调 4 次 LLM (Router+Generate+Reflect+Action) |
| 紧急词误触发 | 检查 `prompts/boundary.py` 的 `EMERGENCY_PATTERNS`，移除模糊关键词 |
