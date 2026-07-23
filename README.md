# 思悟 Agent（Siwu Agent）

> **以毛泽东思想方法论为认知内核的 AI 智能体**
>
> 取"思"与"悟"之意，也暗合"实事求是"的"实"与"实践论"的"践"。

---

## 项目愿景

构建一个以**毛泽东思想方法论**为认知内核的 AI Agent，使其在底层推理流程中贯彻辩证唯物主义、矛盾分析、实践论等核心思维范式。

## 认知循环

```
用户输入
   │
   ▼
① 调查研究   —— 没有调查就没有发言权（联网搜索 + 文件读取）
   │
   ▼
② 矛盾分析   —— 抓主要矛盾，分析矛盾的主要方面
   │
   ▼
③ 理性认识   —— 去粗取精、去伪存真、由此及彼、由表及里
   │
   ▼
④ 决策输出   —— 战略上藐视，战术上重视
   │
   ▼
⑤ 实践检验   —— 多轮递进实验，自动写代码运行并修复
   │
   ▼
⑥ 反思复盘   —— 实践是检验真理的唯一标准
   │
   ▼
判断是否收敛 → 未收敛则重新调查（带上反思提示）
```

---

## 快速开始

### 1. 安装

```bash
pip install siwu-agent
```

如需 Web UI 或扩展功能：
```bash
pip install siwu-agent[web]    # FastAPI REST API
pip install siwu-agent[ui]     # 桌面应用（Flet）
pip install siwu-agent[all]    # 全部功能
```

### 2. 配置 API Key

> ⚠️ **安全提醒**：不要把真实 API key 写在 `config.toml` 里提交到 Git。`config.toml` 中的 key 字段默认是空的模板。请通过环境变量或 `.env` 文件配置。

设置环境变量（推荐）：

```bash
# DeepSeek（默认，推荐）
export DEEPSEEK_API_KEY="sk-xxx"

# 或者 Anthropic Claude
export ANTHROPIC_API_KEY="sk-ant-xxx"

# 可选：Tavily 搜索（不设则不启用网络搜索）
export TAVILY_API_KEY="tvly-xxx"
```

或者创建 `.env` 文件（不会被 Git 追踪）：
```bash
cp .env.example .env
# 编辑 .env 填入你的真实 key
```

环境变量的优先级高于 `config.toml`。

### 3. 运行

```bash
# 标准模式（完整六阶段认知循环）
siwu run "为什么我的开源项目难以吸引贡献者？"

# 深度模式（多轮迭代 + 多视角审查）
siwu run "考虑一群个体进行博弈..." --mode deep

# 提供背景上下文
siwu run "如何提升代码评审质量？" --context "团队 10 人，快速迭代"

# 查看当前配置
siwu config show
```

**桌面应用：**
```bash
siwu ui
# 打开原生桌面窗口，实时展示六阶段认知循环过程
```

**REST API：**
```bash
siwu serve
```

**Python SDK：**
```python
import asyncio
from siwu.core.cognitive_loop import CognitiveLoop

async def main():
    loop = CognitiveLoop()
    response = await loop.run(
        question="为什么我的开源项目难以吸引贡献者？",
        mode="standard",
    )
    print(response.summary)
    for item in response.action_items:
        print(f"- {item}")

asyncio.run(main())
```

---

## 项目结构

```
siwu-agent/
├── siwu/                          # 核心包
│   ├── core/                      # 认知引擎
│   │   ├── cognitive_loop.py      # 认知循环控制器（主入口）
│   │   ├── investigation.py       # 调查研究（Tavily 搜索 + 文件读取）
│   │   ├── contradiction.py       # 矛盾分析
│   │   ├── rational.py            # 理性认识
│   │   ├── decision.py            # 决策引擎
│   │   ├── practice.py            # 实践检验（多轮实验 + 自动修复）
│   │   ├── perspectives.py        # 多视角审查
│   │   └── reflection.py          # 反思引擎（流程控制）
│   ├── llm/                       # LLM 后端
│   │   ├── base.py                # 抽象基类
│   │   ├── claude.py              # Anthropic
│   │   └── deepseek.py            # DeepSeek
│   ├── tools/                     # 工具系统
│   │   ├── filesystem.py          # 文件读写
│   │   └── web_search.py          # Tavily 联网搜索
│   ├── memory/                    # 记忆系统
│   │   └── working_memory.py      # 跨轮次上下文传递
│   ├── api/                       # REST API
│   │   ├── server.py
│   │   └── schemas/models.py      # Pydantic 数据模型
│   ├── ui/                        # 桌面应用（Flet）
│   │   ├── flet_app.py             # 原生窗口 UI
│   │   └── app.py                  # Gradio Web UI（旧版）
│   ├── cli.py                     # 命令行接口
│   └── config.py                  # 配置管理
├── prompts/                       # 各阶段 prompt（.md 可直接编辑）
│   ├── investigation.md
│   ├── contradiction.md
│   ├── rational.md
│   ├── decision.md
│   ├── practice.md
│   └── reflection.md
├── config.toml                    # 默认配置
├── pyproject.toml
└── examples/                      # 实践阶段的工作区
```

---

## 自定义配置

### 编辑 Prompt

直接编辑 `prompts/*.md`，下次运行自动生效，无需改代码。你也可以在运行目录创建自己的 `prompts/` 文件夹覆盖默认值。

### 调整阶段参数

编辑 `config.toml` 中各阶段的 temperature、max_tokens、reasoning_effort：

```toml
[phases.investigation]
temperature = 0.7
max_tokens = 8192
reasoning_effort = "high"

[phases.practice]
practice_rounds = 5    # 实践阶段默认轮数
```

### 多 LLM 后端

默认用 DeepSeek。切到 Anthropic：
```toml
[llm]
provider = "anthropic"
default_model = "claude-sonnet-4-5"
```

---

## 运行模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `fast` | 跳过深度矛盾分析/实践/反思，单轮 | 简单问答 |
| `standard` | 完整认知循环，多轮实践 | 大多数场景 |
| `deep` | 多轮迭代 + 多视角审查 | 复杂分析 |

---

*本项目旨在探索将辩证唯物主义方法论内化为 AI 推理流程的可能性。*
