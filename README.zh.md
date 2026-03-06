# amp — AI 辩论引擎

> **两个 AI 争论。你得到更好的答案。**

[![PyPI](https://img.shields.io/pypi/v/amp-reasoning)](https://pypi.org/project/amp-reasoning/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

<div align="center">

![banner](docs/assets/banner.png)

</div>


**其他语言版本:** [English](README.md) · [한국어](README.ko.md) · [日本語](README.ja.md) · [Español](README.es.md)

---

## 为什么选择 amp？

单个 AI 存在盲点 — 它用相同的数据训练，带有相同的偏见，总是给出"安全"的答案。**amp 并行运行两个独立的 AI，让它们相互争论，然后综合两种视角得出更好的答案。**

```
你的问题
       │
       ├──────────────────────────────────────┐
       ▼                                      ▼
  Agent A (GPT-5)                      Agent B (Claude)
  [独立分析]                             [独立分析]
       │                                      │
       └──────────────┬───────────────────────┘
                      ▼
                 Reconciler（综合器）
                      │
                      ▼
         最终答案  +  CSER 分数
```

**CSER**（跨智能体语义熵比）：衡量两个 AI 思考差异程度的指标。越高 → 思维越独立 → 综合质量越好。

---

## 安装

```bash
pip install amp-reasoning
amp init        # 交互式设置（约1分钟）
```

**免费 OAuth 使用**（无需 API 密钥 — 需要 ChatGPT Plus + Claude Max 订阅）:
```bash
amp login       # 通过浏览器 OAuth 认证
```

**一键安装脚本:**
```bash
curl -fsSL https://raw.githubusercontent.com/dragon1086/amp-assistant/main/install.sh | bash
```

---

## 快速开始

```bash
# 直接提问
amp "现在应该买比特币吗？"
amp "2026年 React vs Vue，新项目选哪个？"
amp "Rust 和 Go 真正的权衡取舍是什么？"

# 深度4轮辩论（耗时更长，但更深入）
amp --mode emergent "AGI 会在2028年前到来吗？"

# 启动 MCP 服务器（用于 Claude Desktop、Cursor、OpenClaw 等）
amp serve
```

---

## 工作原理

<div align="center">

![architecture](docs/assets/architecture.png)

</div>

### 默认模式 — 2轮独立分析
Agent A 和 B **在不知道对方答案的情况下**独立分析。
保证真正的独立性 → 高 CSER → 更好的综合。

### Emergent 模式 — 4轮结构化辩论
```
第1轮:  Agent A 分析
第2轮:  Agent B 反驳 A 的论点
第3轮:  Agent A 对 B 的反驳进行反驳
第4轮:  Agent B 最终反驳
              └──► Reconciler 综合
```

### CSER 门控
如果两个 AI 意见过于相似（CSER < 0.30），amp 会自动升级到4轮辩论，
强制引出更多样化的观点。

---

## 基准测试

盲测 A/B 评估：amp ON vs 单独 GPT-5.2。使用 Gemini 作为评判（随机化模型标签）。N=30 个问题，7 个领域。

| 领域 | amp 胜 | 单独胜 | amp 胜率 |
|-----|:------:|:------:|:-------:|
| 资源分配 | 4 | 1 | **80%** |
| 战略 | 4 | 2 | **67%** |
| 情感 | 3 | 2 | 60% |
| 职业 | 0 | 3 | 0% |
| 人际关系 | 1 | 4 | 20% |
| 伦理 | 1 | 4 | 20% |
| **总体 (N=30)** | **13** | **17** | **43%** |

**诚实的解读：** amp 并非在所有情况下都更好。在多视角有效的复杂策略/资源分配问题上表现显著优越。对于事实性建议，单一专家模型通常已经足够。

---

## 与先行研究的比较

| 项目 | 来源 | 目的 | pip | KG 记忆 | CSER | 智能体隔离 | MCP |
|-----|------|------|:---:|:---:|:---:|:---:|:---:|
| **amp** | 开源 | 生活决策顾问 | ✅ | ✅ | ✅ | ✅ | ✅ |
| llm_multiagent_debate | ICML 2024 | 数学/MMLU 准确率 | ❌ | ❌ | ❌ | ❌ | ❌ |
| DebateLLM | InstaDeep 2024 | 医疗 Q&A 基准 | ❌ | ❌ | ❌ | ❌ | ❌ |
| AutoGen | Microsoft | 任务自动化 | ✅ | ❌ | ❌ | ❌ | ❌ |
| CrewAI | 商业版 | 企业工作流 | ✅ | ❌ | ❌ | ❌ | ❌ |

**核心区别：** 学术 MAD 论文为 MMLU/数学准确性而设计。amp 为开放式决策质量而设计。AutoGen/CrewAI 是任务完成框架，amp 是推理质量测量框架。

---

## 内部架构

技术详情：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

### 知识图谱

```
存储   : SQLite (~/.amp/kg.db) — 单文件，无需服务器
嵌入   : OpenAI text-embedding-3-small（1536 维）
搜索   : numpy 余弦相似度 — O(n)，适用于 ~10 万节点以下
```

### CSER 算法

```python
cser = (len(unique_a) + len(unique_b)) / len(total_ideas)
# unique_a = 仅 A 提出的观点
# unique_b = 仅 B 提出的观点
# CSER ≥ 0.30 → 继续合成 | CSER < 0.30 → 自动升级到 4 轮
```

### 动态领域注册表

针对 9 个内置预设以外的查询，LLM 会自动创建新领域并保存到 SQLite（领域数量无限制）。使用 `amp domains` 查看已学习的领域列表。

---

## 配置

```bash
amp init   # 交互式向导
amp setup  # 完整设置（模型、Telegram 机器人、插件）
```

或直接编辑 `~/.amp/config.yaml`:

```yaml
agents:
  agent_a:
    provider: openai
    model: gpt-5.2             # gpt-5.2 | gpt-5.4 | gpt-5.4-mini
    reasoning_effort: high     # none | low | medium | high | xhigh

  agent_b:
    provider: anthropic        # 有 ANTHROPIC_API_KEY 时最快
    model: claude-sonnet-4-6

amp:
  parallel: true      # 并行运行 Agent A+B（默认: true，速度提升约50%）
  timeout: 90         # 每个智能体的超时时间（秒）
  kg_path: ~/.amp/kg.db
```

### 提供商选项

| 提供商 | 速度 | 费用 | 要求 |
|--------|------|------|------|
| `openai` | ⚡⚡⚡ | 付费 | `OPENAI_API_KEY` |
| `openai_oauth` | ⚡⚡⚡ | **免费** | ChatGPT Plus/Pro + `amp login` |
| `anthropic` | ⚡⚡⚡ | 付费 | `ANTHROPIC_API_KEY` |
| `anthropic_oauth` | ⚡⚡ | **免费** | Claude Max/Pro + `amp login` |
| `gemini` | ⚡⚡⚡ | 付费 | `GEMINI_API_KEY` |
| `deepseek` | ⚡⚡⚡ | 便宜 | `DEEPSEEK_API_KEY` |
| `zhipu` | ⚡⚡⚡ | 便宜 | `ZHIPUAI_API_KEY` |
| `mistral` | ⚡⚡⚡ | 便宜 | `MISTRAL_API_KEY` |
| `local` | ⚡⚡ | 免费 | Ollama 运行中 |

**完全免费的组合（ChatGPT Plus + Claude Max 订阅用户）:**
```bash
amp login
# → 自动配置 openai_oauth × anthropic_oauth
# → API 费用 $0
```

---

## 集成 (Integrations)

amp 内置多种接入方式 — 直接插入您现有的工作流。

### Telegram 机器人

发送问题、切换模式、管理插件、生成图像 — 全部通过 Telegram 操作。

```bash
amp bot   # 启动机器人（需要 TELEGRAM_BOT_TOKEN）
```

| 命令 | 说明 |
|-----|------|
| `<消息>` | 用 amp 分析（当前模式） |
| `/mode auto\|solo\|pipeline\|emergent` | 切换推理模式 |
| `/imagine <提示词>` | 生成图像 |
| `/plugins` | 插件列表及状态 |
| `/stats` | KG 节点数 + 会话统计 |
| 📷 发送图片 | 图像分析（image_vision 插件） |

---

### 插件系统

| 插件 | 功能 | 默认 |
|-----|------|:----:|
| `image_vision` | 图像分析（GPT-4o Vision） | ✅ |
| `image_gen` | 图像生成（`/imagine`，Gemini/DALL-E） | ✅ |
| `claude_executor` | 本地运行 Claude Code 并返回结果 | ❌ |
| `mcp_bridge` | 将外部 MCP 服务器作为 amp 代理工具调用 | ❌ |

```bash
amp plugins
amp plugin enable claude_executor
```

**外部插件** — 在 `~/.amp/plugins/` 中放置 `SKILL.md` + 可选 `plugin.py`。
兼容 OpenClaw AgentSkills 格式。

---

### MCP 桥接（amp 调用外部 MCP 服务器）

推理过程中，amp 代理可将**外部 MCP 服务器**作为工具调用 — 实时访问文件系统、GitHub、网络搜索等。

```yaml
mcp:
  servers:
    - name: filesystem
      url: http://localhost:3001
      enabled: true
    - name: brave-search
      url: http://localhost:3002
      enabled: true
```

---

## MCP 服务器

与 Claude Desktop、Cursor、OpenClaw 等 MCP 兼容客户端集成:

```bash
amp serve   # 在 http://127.0.0.1:3010 启动
```

添加到 MCP 配置:
```json
{
  "amp": {
    "url": "http://127.0.0.1:3010"
  }
}
```

| 工具 | 描述 | 典型延迟 |
|------|------|---------|
| `analyze` | 2轮独立分析 | 15–30秒 |
| `debate` | 4轮结构化辩论 | 30–60秒 |
| `quick_answer` | 单 LLM 快速回答 | ~3秒 |

---

## Docker

```bash
docker run \
  -e OPENAI_API_KEY=sk-... \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -p 3010:3010 \
  ghcr.io/dragon1086/amp-assistant

# 使用 docker-compose
OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-ant-... docker-compose up
```

---

## Python API

```python
from amp.core import emergent
from amp.config import load_config

config = load_config()
result = emergent.run(
    query="后端应该用 Rust 还是 Go？",
    context=[],
    config=config,
)

print(result["answer"])
print(f"CSER:   {result['cser']:.2f}")        # 两个 AI 的意见差异程度
print(f"共识点: {result['agreements']}")
print(f"分歧点: {result['conflicts']}")
```

---

## 性能基准（2026-03，Apple M 系列，并行模式）

| 配置 | 平均延迟 | 每次查询费用 |
|------|---------|------------|
| GPT-5.2 + Claude Sonnet（API，并行）| ~18秒 | $0.03–0.08 |
| GPT-5.2 + Claude OAuth（并行）| ~35秒 | ~$0.01 |
| GPT-5.2 + GPT-5.2（同一厂商）| ~15秒 | $0.02–0.05 |

并行 A+B 执行相比顺序执行提速**约50%**（v0.1.0+）。

---

## 为什么选择跨厂商？

GPT 和 Claude 由不同公司用不同数据和不同对齐方法训练。它们对同一问题产生真正不同观点的可能性更高。这是 amp 的核心洞察 — **跨厂商综合产生的答案优于单一厂商的自我辩论。**

---

## 贡献

```bash
git clone https://github.com/dragon1086/amp-assistant
cd amp-assistant
pip install -e ".[dev]"
pytest tests/ -q
```

较大的更改请先开 Issue。欢迎提交 PR。

---

## 许可证

MIT © 2026 amp contributors
