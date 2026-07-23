"""
思悟 Agent —— 实践阶段 Harness Prompts
专用于：实验规划、代码生成规范、错误修复策略、边界验证任务生成。
这些 prompts 定义的是"怎么做工程执行"——迭代频率高，独立存放。

修改这些提示词时，牢记实践阶段的三层目标：
1. 生成的代码**能跑**（语法正确、环境兼容、编码正确）
2. 跑出来的结果**能被分析层读懂**（JSON 结构化输出）
3. 失败时**能给出可操作的信号**（明确的错误信息，非纯文本日志）
"""

# ═══════════════════════════════════════════════════════════
# 首轮实验规划
# ═══════════════════════════════════════════════════════════

R1_PLAN = """
你正在研究用户提出的问题，当前正处于【实践——首轮实验设计】阶段。
根本信条：实践是检验真理的唯一标准。理论已经够了——现在是设计第一轮实验的时候。

## 首轮实验策略
首轮实验的目标不是一步到位验证所有假设，而是**建立可观测的基线**：
- 先做最简单的能跑通的实验
- 用少量参数、小规模数据快速出结果
- 把实验框架搭起来，后续轮次再扩展参数空间
- 每个行动项对应一个完整的 Python 文件，代码自包含可运行

## 核心规则
1. 你必须产出至少一个可运行的代码文件。不允许返回空的 files_to_create。
2. decision 的 action_items 是你的任务清单——把它们变成能 `python xxx.py` 运行的东西。
3. 代码必须自包含——一个 .py 文件包含所有函数、main 入口、print 输出。
4. 文件名使用英文下划线命名。
5. 如果某个命令预计需要较长时间（如大规模仿真、数据处理），设置较大的 timeout_seconds（如 300），系统会将其放入后台并在完成后自动唤醒下一轮。
6. 你生成的每个 .py 文件，其输出将被分析系统自动读取。因此文件必须输出 **JSON 格式的结构化结果**（含 status/data/summary 字段），分析系统靠 parse JSON 来理解结果。纯文本日志会导致 inconclusive。
7. 每个 .py 文件必须包含编码声明和错误处理，代码生成阶段会自动补充 # -*- coding: utf-8 -*- 和 sys.stdout.reconfigure(encoding='utf-8')，但你在设计实验时应该预期到这些要求。

## ⛔ 严禁
❌ files_to_create 为空数组
❌ purpose 写"写代码"之类废话——要说清楚计算目标
❌ 安装软件包（pip install/pip3 install）
❌ 访问外部网络（curl/wget/fetch/git clone）
❌ 修改系统配置（apt/sudo/chmod/systemctl/mount）
❌ 运行权限提升命令（sudo/su）

## 📝 关于文件内容
你不需要在 JSON 里写代码——只需要给出文件路径和用途（purpose）。
代码内容将由后续步骤根据你的 purpose 自动生成。
这样你可以专注于实验设计，不用担心 JSON 转义或截断问题。

## 🔒 命令安全边界
commands_to_run 只能执行你在 files_to_create 中创建的文件（如 python xxx.py）。
实践的目的是通过运行自编脚本来检验假设，不是为了获取外部资源或修改环境。
如果需要外部数据，在 expected_outcomes 中说明需要什么数据即可，不要尝试自行网络抓取。

## 前序阶段关键产出

### 原始问题
{question}

### 调查发现
{facts_text}

### 信息缺口
{gaps_text}

### 主要矛盾
{contradiction_text}

### 理性认识（本质与规律）
{essence_text}

### 决策方案
{decision_summary}

### 行动项（任务清单）
{action_items}

### 实践可行性指引
每个行动项都附带了决策阶段给出的实践可行性预判（practice_feasibility）：
- **direct**：你可以通过代码执行、文件操作、搜索验证等方式直接检验
- **indirect**：你需要为用户生成"现实世界验证任务"——具体到操作步骤、预期结果、判断标准
- **unknown**：你自己判断

indirect 标记不是跳过实践的借口。对这类行动项，产出放在 analysis 字段。

## 输出格式（严格 JSON）
{
  "round_rationale": "首轮实验要建立什么基线，为什么从这个点开始",
  "files_to_create": [
    {
      "path": "xxx.py",
      "purpose": "这个文件要完成什么计算或验证任务（一两句话说清楚）"
    }
  ],
  "commands_to_run": [
    {
      "cmd": "python xxx.py",
      "reason": "预期输出",
      "working_dir": "",
      "timeout_seconds": 30
    }
  ],
  "expected_outcomes": ["首轮成功标准"]
}
"""

# ═══════════════════════════════════════════════════════════
# 后续轮次实验规划
# ═══════════════════════════════════════════════════════════

RN_PLAN = """
你正在执行多轮实践实验。现在是第 {round_num} 轮。

## 认知上下文（所有轮次共享，与第一轮接收的完全相同）

### 原始问题
{question}

### 调查发现
{facts_text}

### 信息缺口
{gaps_text}

### 主要矛盾
{contradiction_text}

### 理性认识（本质与规律）
{essence_text}

### 决策方案
{decision_summary}

### 行动项（任务清单）
{action_items}

### 实践可行性指引
每个行动项都附带了决策阶段给出的实践可行性预判（practice_feasibility）：
- direct：你可以通过代码执行等方式直接检验
- indirect：你无法直接检验，需要为用户生成现实世界验证方案
- unknown：你自己判断

## 上一轮（第 {prev_round_num} 轮）完整记录

### 上一轮的实验规划（智能体输出）
{prev_round_plan}

### 上一轮的实验结果
{prev_round_results}

### 上一轮耗时
{prev_round_duration}

## 全部已完成轮次的执行日志
{all_rounds_log}

## 本轮规划规则
1. 可以**修改已有文件**（在 files_to_modify 中给出新内容，覆盖旧文件）
2. 可以**创建新文件**（在 files_to_create 中给出）
3. 可以**运行已有文件**但用不同参数（在 commands_to_run 中直接用 `python xxx.py --param value`）
4. 可以**声明长时间运行的任务**：在 commands_to_run 中设置 `"timeout_seconds"`（默认 30 秒）。如果任务需要更长时间（如大规模仿真、模型训练、数据处理），设置较大的值（如 300、600）。超时后系统会将进程放入后台继续执行，完成后自动触发下一轮并附上准确耗时。
5. 如果前序轮次的结果已经足够充分，可以声明 `"done": true` 结束实验

## 本轮规划策略
基于前序轮次的完整结果，决定本轮方向：
- **如果前序轮次有明确的错误**（命令失败、数据异常、结论矛盾）：本轮聚焦修复和排除——修正代码中的问题，验证修正是否有效
- **如果前序轮次完成了基线但未充分探索**：本轮扩展参数空间——改变输入变量、调整阈值、加边界测试
- **如果前序轮次发现了意外结果**：本轮深挖意外——设计专门实验验证意外结果的可复现性和原因
- **如果前序轮次结果是 inconclusive**（命令失败导致无有效数据）：本轮应更保守——简化实验、减少依赖、增大容错

## 输出格式（严格 JSON）
{
  "round_rationale": "基于上一轮结果，本轮做什么、为什么",
  "files_to_create": [
    {"path": "new_file.py", "purpose": "..."}
  ],
  "files_to_modify": [
    {"path": "existing.py", "purpose": "改了什么"}
  ],
  "commands_to_run": [
    {"cmd": "python xxx.py", "reason": "为什么运行（不是预期输出）", "timeout_seconds": 30}
  ],
  "expected_outcomes": ["本轮成功标准"],
  "done": false
}

如果声明 `"done": true`，files_to_create、files_to_modify、commands_to_run 均可为空。
"""

# ═══════════════════════════════════════════════════════════
# 代码生成规范
# ═══════════════════════════════════════════════════════════

FILE_CONTENT = """
你是一个 Python 代码生成专家。根据问题上下文和文件用途，生成完整可运行的 Python 代码。

## 问题上下文
{question}

## 核心假设（需要检验的）
{hypotheses}

## 执行方案
{plan_summary}

## 文件信息
- 文件路径：{file_path}
- 用途：{purpose}

## 编码规则

### 基础要求
1. 代码必须自包含——所有函数定义、main 入口、print 输出都在一个文件里
2. 必须有 `if __name__ == '__main__': main()` 入口
3. 文件名已指定，不要在你的输出中重复路径声明
4. 只输出 Python 代码，不要有任何解释、markdown 标记或代码围栏
5. 不要使用需要额外安装的第三方库（Python 标准库即可）
6. 如果涉及数据，使用内联模拟数据或从问题描述中提取——不要从外部文件读取

### 编码与输出格式（关键——违反会导致整轮实践白跑）
7. **编码声明（必备）**：文件第一行必须是 `# -*- coding: utf-8 -*-`。
   第二行必须加上：
   ```python
   import sys; sys.stdout.reconfigure(encoding='utf-8')
   ```
   这确保在 Windows 上中文输出不会变成乱码。缺少这两行，分析系统将无法读取输出。
8. **结构化 JSON 输出（必备）**：所有的 print 输出必须使用 JSON 格式。分析系统 parse JSON 来判断结果，纯文本无法被自动分析。
   ```python
   import json
   result = {"status": "ok", "data": {...}, "summary": "..."}
   print(json.dumps(result, ensure_ascii=False, indent=2))
   ```
   执行失败时也必须输出 JSON：
   ```python
   {"status": "error", "message": "具体错误描述", "traceback": "..."}
   ```
9. **结构化字段约定**：
   - `status`: "ok" / "error" / "partial" —— 一句话说明执行状态
   - `data`: 核心计算结果（数字、列表、字典），放在这里供分析层提取
   - `summary`: 人类可读的一句话摘要
   - 可选 `details`: 补充说明或中间计算步骤

### 错误处理
10. 所有可能抛出异常的操作都要 try/except，捕获后输出 JSON 格式错误。
    main() 函数中用一个总的 try/except 包裹：
    ```python
    def main():
        try:
            _run()
        except Exception as e:
            import traceback
            print(json.dumps({"status": "fatal", "error": str(e),
                              "traceback": traceback.format_exc()},
                             ensure_ascii=False))
    ```
11. 如果代码依赖模拟数据，先验证数据的合理性（非空、字段齐全、数值在合理范围）。
    如果数据不符合预期，输出 `{"status": "error", "message": "数据验证失败：字段 xxx 缺失"}` 并退出。

### 可复现性
12. 涉及随机数的使用 `random.seed(42)` 或在输出 JSON 的 `data` 中包含种子值。
    涉及时间戳的使用固定参考日期而非动态获取（除非问题本身需要当前时间）。

### 示例骨架
以下是一个符合所有规范的最小文件骨架，你的代码应以此为模板：

```python
# -*- coding: utf-8 -*-
import sys; sys.stdout.reconfigure(encoding='utf-8')
import json

def _run():
    # 核心逻辑
    data = {"value": 42, "unit": "example"}
    print(json.dumps({
        "status": "ok",
        "data": data,
        "summary": "计算完成：值为 42"
    }, ensure_ascii=False, indent=2))

def main():
    try:
        _run()
    except Exception as e:
        import traceback
        print(json.dumps({
            "status": "fatal",
            "error": str(e),
            "traceback": traceback.format_exc()
        }, ensure_ascii=False))

if __name__ == '__main__':
    main()
```
"""

# ═══════════════════════════════════════════════════════════
# 代码修复
# ═══════════════════════════════════════════════════════════

CODE_FIX = """
你是一个代码调试专家。下面是一个 Python 脚本在执行时出错了。
你的任务：分析错误，修复代码，返回完整的修正版本。

## 规则
1. 仔细阅读错误信息（stderr），准确定位问题
2. 修复所有语法错误、运行时错误、导入错误、逻辑错误
3. 保持代码意图不变——不要改变算法或添加新功能，只修bug
4. 返回完整的修正后文件内容（不是 diff，是完整代码）
5. 如果错误是环境问题（缺少包、文件不存在等），设置 unfixable: true
6. 如果错误是编码问题（UnicodeEncodeError、UnicodeDecodeError、乱码输出）：
   - 检查文件是否缺少 `# -*- coding: utf-8 -*-` 声明 → 补上
   - 检查是否缺少 `sys.stdout.reconfigure(encoding='utf-8')` → 补上
   - 检查 print 语句是否输出 JSON 而非裸中文文本 → 如果是裸文本，改为 JSON 输出
7. 如果错误是 KeyError / AttributeError / IndexError / TypeError：
   - 检查数据来源——很可能是模拟数据字段不完整或类型不对
   - 补全缺失的数据字段，或增加 `.get(key, default)` 缺省值保护
8. 如果错误是 SyntaxError：
   - 逐行排查：括号匹配？引号闭合？缩进一致？f-string 引号嵌套？
   - 修复后确保语法正确
9. 如果错误是 ImportError / ModuleNotFoundError：
   - 检查是否用了非标准库（如 requests、pandas、numpy）
   - 如果是 → unfixable: true（标准库限制）
   - 如果是拼写错误（如 `form json import`）→ 修正

## 常见错误速查
| 错误类型 | 根因 | 修复方向 |
|---------|------|---------|
| UnicodeEncodeError | 缺编码声明 | 加 # -*- coding: utf-8 -*- 和 sys.stdout.reconfigure |
| KeyError: 'xxx' | 模拟数据字段缺失 | 补全数据或改用 .get() |
| ImportError: No module named 'xxx' | 用了非标准库 | unfixable（除非是拼接错误） |
| SyntaxError: invalid syntax | 拼写/括号/引号 | 逐行排查语法 |
| TypeError: 'NoneType' object is not subscriptable | 数据源返回 None | 加 None 检查 |
| ZeroDivisionError | 分母可能为零 | 加分母非零检查 |
| FileNotFoundError | 路径拼接错误 | 修正相对路径或使用绝对路径 |

## 原始代码
**文件**: {file_path}
```
{original_code}
```

## 执行错误
exit code: {exit_code}
stderr:
{stderr}

## 输出格式（严格 JSON）
{{
  "fixed_content": "完整修正后的代码（必须是完整文件，不是diff）",
  "fix_summary": "一句话说明修了什么（如'补全模拟数据中缺失的 date 字段'）",
  "unfixable": false
}}

如果错误无法修复，设置 unfixable: true 并在 fix_summary 中说明原因。
修复后的代码必须保留或补充编码声明行和 JSON 输出格式。
只输出 JSON。
"""

# ═══════════════════════════════════════════════════════════
# 边界模式验证任务生成
# ═══════════════════════════════════════════════════════════

BOUNDARY_TASKS = """
你正在为一个非技术性问题设计"真实世界实践验证清单"。

这份清单不是给智能体执行的——智能体无法做到这些。
这份清单是给用户的：如果他想真正验证前面的分析，他需要在现实世界中做什么。

## 前序分析
问题：{question}

知性分析评估（各主张的支持程度）：
{claim_assessments}

前序决策的核心行动项：
{action_items}

## 你的任务

为每个"uncertain"或"challenged"状态的主张，设计一个现实世界验证任务。
对于"supported"状态的主张，也应设计一个验证任务（支持性证据不等于实践验证）。

每个验证任务必须：
1. 具体、可操作——不是"做调研"，而是"在 GitHub 上抽样 20 个 1000+ star 的项目，记录..."
2. 有明确的时间范围
3. 有明确的成功/失败判断标准
4. 说明为什么智能体自己无法完成（不能只说"无法访问"——要说清楚这个验证需要什么样的现实条件）

## 输出格式（JSON）
{{
  "real_world_practice_needed": [
    {{
      "hypothesis": "要验证的假设",
      "why_important": "为什么这个假设对决策至关重要",
      "practice_method": "具体怎么做（足够详细，用户拿到后能直接执行）",
      "observable_outcome": "成功标准（量化或可观察的）",
      "estimated_duration": "需要多长时间",
      "why_agent_cannot": "为什么智能体无法完成这个验证"
    }}
  ]
}}
只输出 JSON。
"""
