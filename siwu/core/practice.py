"""
思悟 Agent —— 实践阶段模块（多轮实验版 v2）
根本原则：实践是检验真理的唯一标准。
多轮实验：规划 → 执行 → 观察 → 再规划 → 再执行 → … → 综合分析

v2 新增：
- 长任务后台执行 + 自动唤醒下一轮（不再硬杀超时进程）
- 全认知上下文传递（每轮都收到与首轮相同的完整上下文 + 上一轮完整结果 + 耗时）
- 命令级超时声明（timeout_seconds），默认 30s
- 后台进程轮询 + 自动触发下一轮
"""
from __future__ import annotations
import asyncio
import json
import time
from typing import Optional
import structlog

from ..api.schemas.models import (
    DecisionReport, PracticeReport, PracticeStep, CognitiveTrace,
    RealWorldPracticeTask,
)
from ..config import PhaseConfig, load_phase_prompt, settings
from ..llm.base import BaseLLM
from ..tools.filesystem import WorkspaceToolkit

from . import practice_harness as harness

log = structlog.get_logger(__name__)

# -- Prompts --

_PRACTICE_PROMPT = """
你正在研究用户提出的问题，当前正处于【实践】阶段。
根本信条：实践是检验真理的唯一标准。

此前各阶段（调查→矛盾分析→理性认识→决策）已经完成，产出了理论认识和你自己的行动方案。
现在不是复述结论的时候——你要亲自把那些结论放回实践中去检验。
决策阶段列出的行动项，是你自己计划要做的事。现在，执行它们。

实践不是一次性的脚本运行。好的实践是一系列递进的实验：
- 先用最小可行实验建立基线
- 再调整参数探索变化趋势
- 然后测试边界条件和极端情况
- 最后综合所有轮次的结果形成判断

## 检验要求
有效的实践检验必须满足三个条件：
1. **有可观测的输出**：实践产出的不是另一段文字，而是具体的结果（数据、文件、计算结果、模拟输出……）
2. **能区分对错**：结果可以明确地支持或削弱前序结论
3. **由问题本质决定形式**：检验形式不做预设——哪种形式最能回答原问题，就选哪种

## 矛盾检验视角
实践的核心任务不仅是验证结论，更是检验矛盾判断：
- 主要矛盾是否真的是主要的？有没有被次要矛盾喧宾夺主？
- 矛盾的主要方面判断是否正确？实践结果是否支持"当前是A主导"这个判断？
- 转化条件是否正确识别？当你在实践中操作这些条件时，矛盾是否如预期那样运动？
- 如果实践结果与矛盾判断不一致——这不是"验证失败"的问题，而是矛盾分析可能出错了。
  在后续的综合分析中，明确记录哪些矛盾判断被实践支持、哪些被削弱、是否出现了新矛盾。
"""





_FINAL_ANALYSIS_PROMPT = """
你正在分析多轮实践实验的完整结果。

## 原始问题
{question}

## 前序假设（理性认识阶段提出）
{hypotheses}

## 决策方案摘要
{decision_summary}

## 实验设计意图
{practice_rationale}

## 全部轮次的执行记录
{all_rounds_log}

## 你的任务
综合分析所有轮次的结果，回答：
1. 多轮实验整体上验证了什么？削弱了什么？
2. 不同参数/条件下的结果有什么规律？
3. 是否有跨轮次的意外发现？
4. 前序假设在经过这一系列实验后，可信度如何变化？
5. 还需要更多实验吗？

## 输出格式（严格 JSON）
{
  "verdict": "confirmed|partially_confirmed|challenged|falsified|inconclusive|execution_error",
  "analysis": "3-5句综合分析",
  "surprises": ["意外发现"],
  "confidence_change": "可信度变化说明",
  "reinvestigation_needed": false,
  "reinvestigation_focus": "",
  "key_findings": ["发现1", "发现2"],
  "contradiction_feedback": [
    {
      "contradiction": "被实践检验的矛盾描述",
      "challenge_type": "falsified|weakened|new_contradiction_found|aspect_shift",
      "evidence": "实践中的什么结果支撑了这个挑战",
      "suggested_revision": "建议如何修正这个矛盾判断"
    }
  ]
}
"""

# ── Boundary mode prompts ───────────────────────────────────

_BOUNDARY_ANALYSIS_PROMPT = """
你正在研究用户提出的问题，当前正处于【实践——知性分析】阶段。

重要前提：这个问题不属于可以通过代码执行来验证的技术类问题。
你无法在此实施真正的实践（真实的用户访谈、A/B测试、组织试点等均无法执行）。
因此，你当前能做的是知性分析——基于调查事实和矛盾分析，对各核心主张进行推断评估。

你的知性分析产出的认识论地位是 V2（交叉一致），不是 V3（实践检验）。
这不是失败，这是诚实的认识论状态。

## 你的任务（三步）

### 第一步：列出需要验证的核心主张
从决策的 action_items 和 strategic_assessment 中提取 3-5 个可检验的核心主张。
每个主张必须是：如果为真，我们能观察到 X；如果为假，我们能观察到 Y。

### 第二步：对每个主张进行知性评估
基于当前已有的调查事实和矛盾分析，评估每个主张：
- supported：多条高可信度事实指向同一方向，且无明显反例
- uncertain：证据混合或不足，结论不确定
- challenged：发现了与主张方向相反的有力证据

注意：不要寻找新的信息（不调用搜索）——只基于前序阶段已有的内容进行评估。

### 第三步：识别意外洞察
在分析过程中，有什么是前序阶段（调查/矛盾/理性/决策）没有充分重视但现在看来值得关注的？

## 前序阶段产出
问题：{question}
理性认识本质：{essence}
主要矛盾：{contradiction}
决策摘要：{decision_summary}
行动项：{action_items}

## 输出格式（JSON）
{{
  "analysis_summary": "3-5句综合推断，明确说明这是知性分析而非实践验证",
  "claim_assessments": [
    {{
      "claim": "核心主张",
      "assessment": "supported|uncertain|challenged",
      "basis": "评估依据（引用具体事实或矛盾分析内容）",
      "if_true": "如果为真应能观察到什么",
      "if_false": "如果为假应能观察到什么"
    }}
  ],
  "unexpected_insights": ["意外洞察1", "意外洞察2"],
  "reinvestigation_needed": false,
  "reinvestigation_focus": "",
  "contradiction_feedback": [
    {
      "contradiction": "被知性分析挑战的矛盾描述",
      "challenge_type": "weakened|new_contradiction_found|aspect_shift",
      "evidence": "证据",
      "suggested_revision": "建议修正方向"
    }
  ]
}}
只输出 JSON。
"""



class PracticeModule:
    """实践阶段 —— 多轮实验：规划 → 执行 → 观察 → 再规划 → … → 综合分析"""

    def __init__(
        self,
        llm: Optional[BaseLLM] = None,
        phase_config: Optional[PhaseConfig] = None,
        workspace: Optional[WorkspaceToolkit] = None,
        max_retries: int = 3,
        practice_rounds: int = 3,
    ):
        if llm is None:
            from ..llm import get_llm
            llm = get_llm()
        self.llm = llm
        self.config = phase_config or PhaseConfig()
        self.workspace = workspace
        self._execution_enabled = True
        self._current_question: str = ""
        self._current_hypotheses: str = ""
        self.max_retries = max_retries
        self.practice_rounds = practice_rounds
        self._background_procs: dict[str, dict] = {}  # cmd → {proc, start_time}

    @property
    def can_execute(self) -> bool:
        return self.workspace is not None and self._execution_enabled

    # ── Main entry ──────────────────────────────────────────

    async def practice(
        self,
        question: str,
        decision_report: DecisionReport,
        trace: CognitiveTrace,
        on_progress: callable = None,
        wm = None,
    ) -> Optional[PracticeReport]:
        """
        实践阶段入口。返回统一的 PracticeReport。
        根据 decision 阶段的 per-item practice_feasibility 自主决定检验方式。
        """
        def _notify(summary: str, data=None):
            if on_progress:
                on_progress("practice", summary, data=data)

        # ── Store question/hypotheses for file content generation ──
        self._current_question = question
        hyps = []
        if trace.rational_synthesis:
            hyps = trace.rational_synthesis.hypotheses[:8]
        self._current_hypotheses = "\n".join(f"- {h}" for h in hyps) if hyps else "（无）"

        # ── Check action item feasibility ──────────────────────
        direct_items = [a for a in decision_report.action_items if a.practice_feasibility == "direct"]
        unknown_items = [a for a in decision_report.action_items if a.practice_feasibility == "unknown"]
        indirect_items = [a for a in decision_report.action_items if a.practice_feasibility == "indirect"]
        has_executable = bool(direct_items or unknown_items)

        log.info("practice.start",
                 n_actions=len(decision_report.action_items),
                 n_direct=len(direct_items), n_indirect=len(indirect_items),
                 n_unknown=len(unknown_items),
                 has_workspace=self.workspace is not None)

        if not has_executable:
            return await self._simulated_practice(question, decision_report, trace)

        # ── Execution mode ─────────────────────────────────────

        if not self.workspace:
            return await self._simulated_practice(question, decision_report, trace)

        all_steps: list[PracticeStep] = []
        all_outcomes: list[str] = []
        all_unexpected: list[str] = []
        all_success: list[str] = []
        all_failure: list[str] = []
        round_summaries: list[str] = []
        full_execution_log: list[str] = []
        round_contexts: list[dict] = []  # full context from each round for cumul. passing

        overall_rationale = ""

        # ── Round 1: full plan from cognitive context ────────
        r1_plan = await self._plan_round1(question, decision_report, trace, wm=wm)
        overall_rationale = r1_plan.get("round_rationale", "")

        t0 = time.time()
        r1_steps, r1_outcomes, r1_unexpected, r1_success, r1_failure, r1_log, r1_ok = \
            await self._execute_round(r1_plan, round_num=1)
        r1_duration = time.time() - t0

        all_steps.extend(r1_steps)
        all_outcomes.extend(r1_outcomes)
        all_unexpected.extend(r1_unexpected)
        all_success.extend(r1_success)
        all_failure.extend(r1_failure)
        full_execution_log.append(f"=== 第 1 轮 (耗时 {r1_duration:.1f}s) ===\n{r1_log}")

        round_contexts.append({
            "round_num": 1,
            "plan_json": json.dumps(r1_plan, ensure_ascii=False, indent=2),
            "results": r1_log,
            "duration": f"{r1_duration:.1f}s",
        })
        round_summaries.append(
            self._summarise_round(1, r1_plan, r1_outcomes, r1_unexpected, r1_failure, r1_ok)
        )

        created_files = list(r1_plan.get("files_to_create", []))

        # ── Rounds 2 .. N ────────────────────────────────────
        for r in range(2, self.practice_rounds + 1):
            # Collect any completed background processes from previous rounds
            bg_results = await self._wait_for_background()
            if bg_results:
                for bg in bg_results:
                    bg_log = (
                        f"[后台进程完成] {bg['cmd']}\n"
                        f"  耗时: {bg['duration']:.1f}s  exit={bg['returncode']}\n"
                        f"  stdout: {bg['stdout'][:800]}\n"
                        f"  stderr: {bg['stderr'][:400]}"
                    )
                    full_execution_log.append(bg_log)
                    all_steps.append(PracticeStep(
                        description=f"后台进程完成：{bg['cmd'][:80]}",
                        action_taken=f"等待 {bg['duration']:.1f}s 后完成",
                        observed_result=(
                            f"exit={bg['returncode']}\n{bg['stdout'][:300]}"
                        ),
                        matched_expectation=bg['returncode'] == 0,
                    ))
                    if bg['returncode'] == 0:
                        all_success.append(f"后台完成：{bg['cmd'][:60]} ({bg['duration']:.1f}s)")
                    else:
                        all_failure.append(
                            f"后台失败 exit={bg['returncode']}：{bg['cmd'][:60]}"
                        )

            # Build full context for next-round planning
            ctx = self._build_next_round_context(
                round_num=r, question=question,
                decision_report=decision_report, trace=trace,
                round_contexts=round_contexts,
                full_execution_log=full_execution_log,
            )

            rn_plan = await self._plan_next_round(ctx, created_files)

            if rn_plan.get("done"):
                log.info("practice.rounds_done_early", rounds_completed=r - 1)
                all_steps.append(PracticeStep(
                    description=f"实验完成（共 {r - 1} 轮）",
                    action_taken="实验数据已充分，不需要更多轮次",
                    observed_result=rn_plan.get("round_rationale", "已获得足够数据"),
                    matched_expectation=True,
                ))
                break

            # Apply any file modifications
            for mod in rn_plan.get("files_to_modify", []):
                mpath = mod.get("path", "")
                mcontent = mod.get("content", "")
                mpurpose = mod.get("purpose", "") or mod.get("reason", "")
                # Generate content from purpose if not inline
                if not mcontent and mpurpose:
                    mcontent = await self._generate_file_content(
                        path=mpath, purpose=mpurpose, plan=rn_plan,
                    )
                if mpath and mcontent:
                    try:
                        wr = await self.workspace.write.run(path=mpath, content=mcontent)
                        if wr.ok:
                            full_execution_log.append(
                                f"[MODIFY] {mpath}: {mod.get('reason', mpurpose)}"
                            )
                    except Exception as e:
                        log.warning("practice.modify_error", path=mpath, error=str(e))

            # Add any new files
            for fc in rn_plan.get("files_to_create", []):
                created_files.append(fc)

            # Execute round
            t0 = time.time()
            rn_steps, rn_outcomes, rn_unexpected, rn_success, rn_failure, rn_log, rn_ok = \
                await self._execute_round(rn_plan, round_num=r)
            rn_duration = time.time() - t0

            all_steps.extend(rn_steps)
            all_outcomes.extend(rn_outcomes)
            all_unexpected.extend(rn_unexpected)
            all_success.extend(rn_success)
            all_failure.extend(rn_failure)
            full_execution_log.append(
                f"=== 第 {r} 轮 (耗时 {rn_duration:.1f}s) ===\n{rn_log}"
            )

            round_contexts.append({
                "round_num": r,
                "plan_json": json.dumps(rn_plan, ensure_ascii=False, indent=2),
                "results": rn_log,
                "duration": f"{rn_duration:.1f}s",
            })
            round_summaries.append(
                self._summarise_round(r, rn_plan, rn_outcomes, rn_unexpected, rn_failure, rn_ok)
            )

        # ── Final analysis across all rounds ─────────────────
        all_log_text = "\n\n".join(full_execution_log)
        analysis = await self._analyze_all_rounds(
            question=question,
            decision_report=decision_report,
            trace=trace,
            rationale=overall_rationale,
            all_rounds_log=all_log_text,
        )

        # ── Build report ─────────────────────────────────────
        total_rounds = len(round_summaries)
        summary = ""
        if analysis:
            verdict = analysis.get("verdict", "unknown")
            summary = f"[{verdict}] {analysis.get('analysis', '')}"
            if analysis.get("surprises"):
                for s in analysis["surprises"][:3]:
                    if s not in all_unexpected:
                        all_unexpected.append(s)
            if analysis.get("reinvestigation_needed"):
                summary += (
                    f" → 建议重新调查：{analysis.get('reinvestigation_focus', '')[:80]}"
                )
            if analysis.get("key_findings"):
                summary += " | 关键发现：" + "；".join(analysis["key_findings"][:3])
        else:
            summary = overall_rationale or f"完成 {total_rounds} 轮实验"
            if all_success:
                summary += f"；{len(all_success)} 项成功"
            if all_failure:
                summary += f"；{len(all_failure)} 项失败"

        summary = f"[共 {total_rounds} 轮实验] {summary}"

        log.info("practice.done",
                 rounds=total_rounds,
                 verdict=analysis.get("verdict") if analysis else "no_analysis",
                 unexpected=len(all_unexpected))

        # ── Determine mode and confidence_ceiling ──────────
        if direct_items:
            if indirect_items:
                p_mode = "partial"
                ceiling = "V2"
            else:
                p_mode = "executed"
                ceiling = "V3"
        else:
            p_mode = "epistemic_only"
            ceiling = "V2"

        report = PracticeReport(
            mode=p_mode,
            confidence_ceiling=ceiling,
            steps_taken=all_steps,
            observed_outcomes=all_outcomes,
            unexpected_findings=all_unexpected,
            practice_summary=summary,
            success_indicators=all_success[:10],
            failure_indicators=all_failure[:10],
            contradiction_feedback=analysis.get("contradiction_feedback", []) if analysis else [],
        )
        if analysis:
            report.success_indicators.append(
                f"实验结论：{analysis.get('verdict', '')}"
            )
            report.failure_indicators.append(
                f"可信度变化：{analysis.get('confidence_change', '')}"
            )
        return report
    # ── Round planning ──────────────────────────────────────

    async def _plan_round1(self, question: str, decision: DecisionReport,
                           trace: CognitiveTrace, wm=None) -> dict:
        """Full-context first-round planning."""
        facts_lines = []
        if trace.investigation:
            for f in trace.investigation.facts[:6]:
                facts_lines.append(f"- [{f.credibility:.0%}] {f.content[:120]}")
        gaps_lines = []
        if trace.investigation:
            for g in trace.investigation.gaps[:5]:
                gaps_lines.append(f"- [{g.importance}] {g.description[:120]}")
        contradiction_text = "（未识别）"
        if trace.contradictions and trace.contradictions.principal_contradiction:
            contradiction_text = trace.contradictions.principal_contradiction.description[:300]
        essence_text = "（未形成）"
        if trace.rational_synthesis:
            essence_text = trace.rational_synthesis.essence[:300]
        action_text = "\n".join(
            f"- [P{a.priority}] {a.description} [feasibility: {a.practice_feasibility}]" for a in decision.action_items[:6]
        ) or "（无）"
        decision_summary = decision.summary or decision.strategic_assessment[:400]

        prompt = harness.R1_PLAN
        # Skill injection: prepend validated practice skill templates
        skill_prefix = ""
        if wm:
            try:
                skill_ctx = wm.get("_skill_context_practice", "")
                if skill_ctx:
                    skill_prefix = (
                        "## 可用技能（优先使用，无需从零实现）\n"
                        + skill_ctx + "\n\n"
                        "请优先使用上述技能提供的代码模板。如果技能完全满足需求，可以直接复用其代码框架，只需调整输入参数。\n"
                        "如果没有匹配的技能，按照标准流程自行实现。\n\n---\n\n"
                    )
            except Exception:
                pass
        prompt = skill_prefix + prompt
        prompt = prompt.replace("{question}", question)
        prompt = prompt.replace("{facts_text}", "\n".join(facts_lines) or "（无）")
        prompt = prompt.replace("{gaps_text}", "\n".join(gaps_lines) or "（无）")
        prompt = prompt.replace("{contradiction_text}", contradiction_text)
        prompt = prompt.replace("{essence_text}", essence_text)
        prompt = prompt.replace("{decision_summary}", decision_summary)
        prompt = prompt.replace("{action_items}", action_text)

        plan = await self._call_planner(prompt,
            "请基于前序认知产出，设计第一轮实验。目标是建立可观测基线。"
            "每个需要代码的行动项必须产出完整可运行 Python 代码。")

        # Fallback: if empty, retry harsher
        if (not plan.get("files_to_create") and not plan.get("commands_to_run")
                and decision.action_items):
            log.info("practice.r1_empty_retrying")
            retry_prompt = f"""直接为以下行动项编写可运行代码：

## 问题
{question}

## 行动项
{action_text}

输出 JSON：{{"round_rationale":"...", "files_to_create":[{{"path":"x.py","purpose":"这个文件要做什么"}}], "commands_to_run":[{{"cmd":"python x.py","reason":"...","working_dir":"","timeout_seconds":30}}], "expected_outcomes":["..."]}}

注意：不需要在JSON中写代码，只需要purpose描述。代码会自动生成。"""
            plan = await self._call_planner(retry_prompt,
                "请把上述行动项直接翻译为可运行的 Python 代码文件。")
        return plan

    async def _plan_next_round(self, ctx: dict, existing_files: list[dict]) -> dict:
        """Plan round 2+ with full cognitive context + all previous round results."""
        prompt = harness.RN_PLAN
        for key, value in ctx.items():
            prompt = prompt.replace("{" + key + "}", str(value))

        files_list = "\n".join(
            f"- {f.get('path', '?')} ({f.get('reason', '')})"
            for f in existing_files[-8:]
        ) or "（无）"

        user_msg = (
            f"原始问题：{ctx.get('question', '')}\n\n"
            f"已有文件：\n{files_list}\n\n"
            f"基于全部前序轮次的实验结果和完整认知上下文，规划第 {ctx.get('round_num', '?')} 轮实验。"
            f"如果数据已充分，设置 done: true。"
        )
        return await self._call_planner(prompt, user_msg)

    async def _call_planner(self, system_prompt: str, user_msg: str) -> dict:
        try:
            resp = await self.llm.call(
                messages=[{"role": "user", "content": user_msg}],
                system=system_prompt,
                temperature=getattr(self.config, "temperature", 0.4),
                max_tokens=getattr(self.config, "max_tokens", 8192),
            )
            raw = resp.content.strip()
            plan = self._parse_json_safe(raw)
            if not plan:
                import re
                fixed = re.sub(r'(?<!\\)"(?=[^"]*$)', '"', raw)
                fixed = fixed.rstrip() + '\n}]}'
                plan = self._parse_json_safe(fixed)
            log.info("practice.plan_parsed",
                     has_rationale=bool(plan.get("round_rationale")),
                     n_files=len(plan.get("files_to_create", [])),
                     n_cmds=len(plan.get("commands_to_run", [])),
                     done=plan.get("done"))
            plan.setdefault("round_rationale", "")
            plan.setdefault("files_to_create", [])
            plan.setdefault("commands_to_run", [])
            plan.setdefault("expected_outcomes", [])
            return plan
        except Exception as e:
            log.warning("practice.plan_parse_error", error=str(e))
            return {
                "round_rationale": f"规划解析失败：{str(e)[:100]}",
                "files_to_create": [],
                "commands_to_run": [],
                "expected_outcomes": [],
            }

    # ── Round execution ─────────────────────────────────────

    async def _execute_round(self, plan: dict, round_num: int) -> tuple:
        """Execute one round: write files → run commands → fix & retry → return results."""
        steps: list[PracticeStep] = []
        outcomes: list[str] = []
        unexpected: list[str] = []
        success_indicators: list[str] = []
        failure_indicators: list[str] = []
        log_parts: list[str] = []
        all_ok = True

        rationale = plan.get("round_rationale", "")
        if rationale:
            steps.append(PracticeStep(
                description=f"第{round_num}轮实验设计",
                action_taken=rationale,
                observed_result=f"开始第{round_num}轮",
                matched_expectation=True,
            ))

        # Write files — generate content from purpose if needed
        for fc in plan.get("files_to_create", []):
            path = fc.get("path", "")
            file_content = fc.get("content", "")
            purpose = fc.get("purpose", "") or fc.get("reason", "")
            if not path:
                continue
            # Generate content if plan only gave purpose (post-decoupling)
            if not file_content and purpose:
                file_content = await self._generate_file_content(
                    path=path, purpose=purpose, plan=plan,
                )
            if not file_content:
                continue
            try:
                result = await self.workspace.write.run(path=path, content=file_content)
                if result.ok:
                    log_parts.append(f"[CREATE] {path} ({len(file_content)} chars) — {purpose}")
                    steps.append(PracticeStep(
                        description=f"创建：{path}",
                        action_taken=f"写入 {len(file_content)} chars",
                        observed_result=f"创建成功（{purpose}）",
                        matched_expectation=True,
                    ))
                else:
                    failure_indicators.append(f"创建失败：{path} — {result.error}")
                    log_parts.append(f"[CREATE FAIL] {path} — {result.error}")
                    all_ok = False
            except Exception as e:
                log.error("practice.create_error", path=path, error=str(e))
                failure_indicators.append(f"创建异常：{path}")
                unexpected.append(f"写入 {path} 异常：{e}")
                all_ok = False

        cmd_results: dict[str, dict] = {}
        has_background = False

        # Run commands
        for cmd_plan in plan.get("commands_to_run", []):
            cmd = cmd_plan.get("cmd", "")
            reason = cmd_plan.get("reason", "")
            if not cmd:
                continue

            # ── Safety check: block dangerous commands ──
            cmd_lower = cmd.lower()
            blocked = False
            for pattern in self._effective_blocked_patterns():
                if pattern in cmd_lower:
                    blocked = True
                    break
            if blocked:
                log.warning("practice.cmd_blocked", cmd=cmd[:100])
                failure_indicators.append(f"已阻止危险命令：{cmd}")
                unexpected.append(
                    f"实践阶段阻止了以下命令（涉及环境修改或外部交互，超出实践验证范围）：{cmd}\n"
                    f"实践的目标是检验前序认识——编写和运行分析脚本、验证假设即可，"
                    f"不应安装软件包、访问外部网络或修改系统配置。"
                )
                all_ok = False
                continue

            try:
                timeout_seconds = float(cmd_plan.get("timeout_seconds", 30))
                exec_result = await self._execute(cmd, timeout_seconds=timeout_seconds)
                cmd_results[cmd] = exec_result

                if exec_result.get("background"):
                    # Process running in background — will be collected next round
                    has_background = True
                    log_parts.append(
                        f"[BACKGROUND] {cmd}\n"
                        f"  {exec_result.get('message', '')}"
                    )
                    steps.append(PracticeStep(
                        description=f"后台执行：{cmd}",
                        action_taken=cmd,
                        observed_result=exec_result.get("message", ""),
                        matched_expectation=True,
                    ))
                    unexpected.append(
                        f"后台执行：{cmd} — {exec_result.get('message', '')}"
                    )
                    continue

                stdout_s = exec_result['stdout'][:800]
                stderr_s = exec_result['stderr'][:400]

                log_parts.append(
                    f"[CMD] {cmd}\n  exit={exec_result['returncode']}\n"
                    f"  stdout: {stdout_s}\n  stderr: {stderr_s}"
                )
                outcome_text = f"执行：{cmd}\nstdout: {stdout_s}\nstderr: {stderr_s}"

                if exec_result["returncode"] == 0:
                    outcomes.append(f"OK {cmd}\n{stdout_s[:200]}")
                    success_indicators.append(f"{cmd}: {reason}" if reason else cmd)
                    steps.append(PracticeStep(
                        description=f"执行：{cmd}",
                        action_taken=cmd,
                        observed_result=outcome_text,
                        matched_expectation=True,
                    ))
                else:
                    all_ok = False
                    failure_indicators.append(
                        f"失败 exit={exec_result['returncode']}：{cmd}"
                    )
                    outcomes.append(f"FAIL {cmd}")
                    steps.append(PracticeStep(
                        description=f"执行失败：{cmd}",
                        action_taken=cmd,
                        observed_result=outcome_text,
                        matched_expectation=False,
                    ))
                    unexpected.append(
                        f"命令失败：{cmd}\n{exec_result['stderr'][:300]}"
                    )
            except Exception as e:
                log.error("practice.exec_error", cmd=cmd, error=str(e))
                cmd_results[cmd] = {
                    "returncode": -1, "stdout": "", "stderr": str(e), "background": False,
                }
                all_ok = False
                failure_indicators.append(f"执行异常：{cmd}")
                unexpected.append(f"执行异常 {cmd}：{e}")

        # Retry loop for failed commands (skip background ones)
        retry_count = 0
        while retry_count < self.max_retries:
            failed = [
                (cp, cmd_results.get(cp.get("cmd", ""), {}))
                for cp in plan.get("commands_to_run", [])
                if cp.get("cmd", "")
                and not cmd_results.get(cp.get("cmd", ""), {}).get("background")
                and cmd_results.get(cp.get("cmd", ""), {}).get("returncode", 0) != 0
            ]
            if not failed:
                break

            retry_count += 1
            log.info("practice.retry", round=round_num, attempt=retry_count,
                     n_failed=len(failed))
            steps.append(PracticeStep(
                description=f"修复重试 (第{round_num}轮，{retry_count}/{self.max_retries}次)",
                action_taken=f"发现 {len(failed)} 条命令失败，自动修复",
                observed_result="分析错误并修复代码…",
                matched_expectation=True,
            ))

            for cp, _ in failed:
                cmd = cp.get("cmd", "")
                file_path = self._infer_file_from_cmd(cmd)
                if not file_path:
                    continue
                current_code = ""
                try:
                    rr = await self.workspace.read.run(path=file_path)
                    if rr.ok:
                        current_code = rr.content
                except Exception:
                    pass
                if not current_code:
                    continue

                syntax_ok, syntax_err = await self._check_syntax(file_path)
                if not syntax_ok:
                    log_parts.append(f"[SYNTAX-ERROR] {file_path}: {syntax_err[:200]}")
                    outcomes.append(f"FAIL-SYNTAX {cmd}: {syntax_err[:100]}")
                    failure_indicators.append(f"语法错误：{file_path}")
                    cmd_results[cmd] = {"returncode": -1, "stdout": "", "stderr": syntax_err, "background": False}
                    continue

                res = cmd_results.get(cmd, {})
                fix = await self._fix_code(
                    file_path=file_path,
                    original_code=current_code[:6000],
                    stderr=res.get("stderr", "")[:2000],
                    exit_code=str(res.get("returncode", -1)),
                )
                if fix and fix.get("fixed_content") and not fix.get("unfixable"):
                    try:
                        wr = await self.workspace.write.run(
                            path=file_path, content=fix["fixed_content"]
                        )
                        if wr.ok:
                            log_parts.append(
                                f"[FIX] {file_path}: {fix.get('fix_summary', '')}"
                            )
                            steps.append(PracticeStep(
                                description=f"修复代码：{file_path}",
                                action_taken=fix.get("fix_summary", ""),
                                observed_result="重新执行…",
                                matched_expectation=True,
                            ))
                            timeout_s = float(cp.get("timeout_seconds", 30))
                            re_res = await self._execute(cmd, timeout_seconds=timeout_s)
                            cmd_results[cmd] = re_res
                            log_parts.append(
                                f"[CMD-RETRY] {cmd}\n  exit={re_res['returncode']}\n"
                                f"  stdout: {re_res['stdout'][:800]}"
                            )
                            if re_res["returncode"] == 0:
                                success_indicators.append(
                                    f"修复成功：{fix.get('fix_summary', '')}"
                                )
                                outcomes.append(f"RETRY-OK {cmd}")
                                steps.append(PracticeStep(
                                    description=f"修复后成功：{cmd}",
                                    action_taken=cmd,
                                    observed_result=(
                                        f"修复 {fix.get('fix_summary', '')}，执行成功"
                                    ),
                                    matched_expectation=True,
                                ))
                                failure_indicators = [
                                    x for x in failure_indicators if cmd not in x
                                ]
                            else:
                                failure_indicators.append(f"修复后仍失败：{cmd}")
                                unexpected.append(
                                    f"修复 ({fix.get('fix_summary', '')}) 后仍失败：{cmd}"
                                )
                    except Exception as e:
                        log.error("practice.fix_write_error", path=file_path, error=str(e))
                elif fix and fix.get("unfixable"):
                    unfix_reason = fix.get("fix_summary", "未知原因")
                    failure_indicators.append(f"不可修复: {file_path} - {unfix_reason}")
                    log_parts.append(f"[UNFIXABLE] {file_path}: {unfix_reason}")
                    outcomes.append(f"FAIL-UNFIXABLE {cmd}: {unfix_reason}")
                    steps.append(PracticeStep(
                        description=f"无法修复：{file_path}",
                        action_taken="尝试修复失败",
                        observed_result=f"失败原因: {unfix_reason}",
                        matched_expectation=False,
                    ))

        if has_background:
            log_parts.append("[INFO] 有后台进程运行中，下一轮将自动收集结果")

        log_text = "\n".join(log_parts) if log_parts else "（空）"
        return (steps, outcomes, unexpected, success_indicators,
                failure_indicators, log_text, all_ok)

    # ── Context builder for next-round planning ──────────────

    def _build_next_round_context(
        self, round_num: int, question: str,
        decision_report: DecisionReport, trace: CognitiveTrace,
        round_contexts: list[dict], full_execution_log: list[str],
    ) -> dict:
        """Build the full context dict for harness.RN_PLAN template.

        Includes: the SAME cognitive context as Round 1 + the previous round's
        complete plan & results & duration + all rounds' cumulative execution log.
        """
        # ── Cognitive context (identical to Round 1) ──────────
        facts_lines = []
        if trace.investigation:
            for f in trace.investigation.facts[:6]:
                facts_lines.append(f"- [{f.credibility:.0%}] {f.content[:120]}")
        gaps_lines = []
        if trace.investigation:
            for g in trace.investigation.gaps[:5]:
                gaps_lines.append(f"- [{g.importance}] {g.description[:120]}")
        contradiction_text = "（未识别）"
        if trace.contradictions and trace.contradictions.principal_contradiction:
            contradiction_text = (
                trace.contradictions.principal_contradiction.description[:300]
            )
        essence_text = "（未形成）"
        if trace.rational_synthesis:
            essence_text = trace.rational_synthesis.essence[:300]
        action_text = "\n".join(
            f"- [P{a.priority}] {a.description} [feasibility: {a.practice_feasibility}]"
            for a in decision_report.action_items[:6]
        ) or "（无）"
        decision_summary = (
            decision_report.summary or decision_report.strategic_assessment[:400]
        )

        # ── Previous round context ────────────────────────────
        prev = round_contexts[-1] if round_contexts else {}
        prev_round_num = prev.get("round_num", round_num - 1)
        prev_plan = prev.get("plan_json", "（无）")
        prev_results = prev.get("results", "（无）")
        prev_duration = prev.get("duration", "未知")

        # ── All rounds cumulative log ─────────────────────────
        all_log = "\n\n".join(full_execution_log) if full_execution_log else "（无）"

        return {
            "round_num": str(round_num),
            "question": question,
            "facts_text": "\n".join(facts_lines) or "（无）",
            "gaps_text": "\n".join(gaps_lines) or "（无）",
            "contradiction_text": contradiction_text,
            "essence_text": essence_text,
            "decision_summary": decision_summary,
            "action_items": action_text,
            "prev_round_num": str(prev_round_num),
            "prev_round_plan": prev_plan[:3000],
            "prev_round_results": prev_results[:3000],
            "prev_round_duration": prev_duration,
            "all_rounds_log": all_log[:4000],
        }

    # ── Round summary for next-round planning ───────────────

    def _summarise_round(self, r: int, plan: dict, outcomes: list[str],
                         unexpected: list[str], failures: list[str],
                         all_ok: bool) -> str:
        parts = [f"## 第 {r} 轮"]
        rationale = plan.get("round_rationale", "")
        if rationale:
            parts.append(f"目的：{rationale[:200]}")
        cmds = plan.get("commands_to_run", [])
        if cmds:
            parts.append(f"执行了 {len(cmds)} 条命令")
        if outcomes:
            parts.append("关键输出：")
            for o in outcomes[:5]:
                parts.append(f"  {o[:200]}")
        if unexpected:
            parts.append("意外发现：")
            for u in unexpected[-5:]:
                parts.append(f"  {u[:200]}")
        if failures:
            parts.append(f"失败项 ({len(failures)})：")
            for f in failures[-3:]:
                parts.append(f"  {f[:150]}")
        status = "✓ 全部成功" if all_ok else "✗ 存在失败"
        parts.append(f"状态：{status}")
        return "\n".join(parts)

    # ── Final analysis ──────────────────────────────────────

    async def _analyze_all_rounds(
        self, question: str, decision_report: DecisionReport,
        trace: CognitiveTrace, rationale: str, all_rounds_log: str,
    ) -> Optional[dict]:
        """Analyze the full multi-round experiment log."""
        try:
            hypotheses_text = ""
            if trace.rational_synthesis:
                hypotheses_text = "\n".join(
                    f"- {h}" for h in trace.rational_synthesis.hypotheses[:5]
                )
            decision_summary = (
                decision_report.summary or decision_report.strategic_assessment[:300]
            )

            prompt = _FINAL_ANALYSIS_PROMPT
            prompt = prompt.replace("{question}", question)
            prompt = prompt.replace("{hypotheses}", hypotheses_text or "（未提出）")
            prompt = prompt.replace("{decision_summary}", decision_summary)
            prompt = prompt.replace(
                "{practice_rationale}", rationale or "（未记录）"
            )
            prompt = prompt.replace("{all_rounds_log}", all_rounds_log[:6000])

            resp = await self.llm.call(
                messages=[{
                    "role": "user",
                    "content": (
                        "请综合分析以上全部轮次的实验结果。"
                        "注意区分代码执行错误和假设检验结果。"
                    ),
                }],
                system=prompt,
                temperature=0.3,
                max_tokens=1024,
            )
            raw = resp.content.strip()
            while raw.startswith("```"):
                idx = raw.find("\n")
                raw = raw[idx+1:] if idx >= 0 else ""
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip().rstrip("`")
            analysis = json.loads(raw)
            log.info("practice.analysis", verdict=analysis.get("verdict"))
            return analysis
        except (json.JSONDecodeError, Exception) as e:
            log.warning("practice.analysis_error", error=str(e))
            return {
                "verdict": "inconclusive",
                "analysis": (
                    f"多轮实验完成但分析解析失败。"
                    f"执行摘要：{all_rounds_log[:300]}"
                ),
                "surprises": [],
                "confidence_change": "无法判断",
                "reinvestigation_needed": False,
                "reinvestigation_focus": "",
                "key_findings": [],
            }

    # ── Background process management ────────────────────────

    async def _collect_background_results(self) -> list[dict]:
        """Check all background processes. Return list of completed ones with results."""
        completed: list[dict] = []
        still_running: dict[str, dict] = {}
        for cmd, info in self._background_procs.items():
            proc = info["proc"]
            if proc.returncode is not None:
                # Process finished — collect output
                try:
                    stdout, stderr = await proc.communicate()
                except Exception:
                    stdout, stderr = b"", "进程通信异常".encode()
                duration = time.time() - info["start_time"]
                result = {
                    "cmd": cmd,
                    "returncode": proc.returncode,
                    "stdout": (stdout or b"").decode("utf-8", errors="replace"),
                    "stderr": (stderr or b"").decode("utf-8", errors="replace"),
                    "duration": duration,
                }
                completed.append(result)
                log.info("practice.background_completed", cmd=cmd[:80],
                         duration=f"{duration:.1f}s", returncode=proc.returncode)
            else:
                still_running[cmd] = info
        self._background_procs = still_running
        return completed

    async def _wait_for_background(self, poll_interval: float = 2.0,
                                   hard_timeout: float = 600.0) -> list[dict]:
        """Wait for background processes to complete (polling). Returns completed ones.

        On hard timeout (default 10 min), remaining processes are forcibly killed.
        """
        if not self._background_procs:
            return []
        waited = 0.0
        while waited < hard_timeout:
            completed = await self._collect_background_results()
            if completed:
                return completed
            await asyncio.sleep(poll_interval)
            waited += poll_interval
        # Hard timeout — forcibly terminate remaining processes
        remaining = list(self._background_procs.keys())
        for cmd, info in self._background_procs.items():
            try:
                info["proc"].kill()
            except Exception:
                pass
        self._background_procs = {}
        log.warning("practice.background_hard_timeout",
                    cmds=remaining, timeout=hard_timeout)
        return []

    # ── Command execution ────────────────────────────────────

    async def _check_syntax(self, file_path: str) -> tuple[bool, str]:
        ws = str(self.workspace.workspace) if self.workspace else "."
        child_env = {**__import__("os").environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "py_compile", file_path,
                cwd=ws, env=child_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            stderr_s = stderr.decode("utf-8", errors="replace")
            return proc.returncode == 0, stderr_s
        except Exception as e:
            return False, str(e)


    async def _execute(self, cmd: str, timeout_seconds: float = 30.0) -> dict:
        """Execute a shell command.

        If the command exceeds timeout_seconds, it is NOT killed.
        Instead it runs in background and its results will be collected
        by _wait_for_background() before the next round starts.
        """
        ws = str(self.workspace.workspace) if self.workspace else "."
        try:
            import os as _os
            child_env = {**_os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=ws,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=child_env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout_seconds,
                )
                raw_stdout = stdout or b""
                raw_stderr = stderr or b""
                stdout_s = raw_stdout.decode("utf-8", errors="replace")
                stderr_s = raw_stderr.decode("utf-8", errors="replace")
                if stdout_s.count("\ufffd") > len(stdout_s) * 0.3:
                    try:
                        stdout_s = raw_stdout.decode("gbk", errors="replace")
                        stderr_s = raw_stderr.decode("gbk", errors="replace")
                    except Exception:
                        pass
                return {
                    "returncode": proc.returncode or 0,
                    "stdout": stdout_s,
                    "stderr": stderr_s,
                    "background": False,
                }
            except asyncio.TimeoutError:
                # Don't kill — let it run, store handle for later collection
                self._background_procs[cmd] = {
                    "proc": proc,
                    "start_time": time.time(),
                }
                log.info("practice.background_launched",
                         cmd=cmd[:80], timeout=timeout_seconds)
                return {
                    "stdout": "",
                    "stderr": "",
                    "exit": -1,
                    "background": True,
                    "cmd": cmd,
                }
            except Exception as e:
                return {
                    "stdout": "",
                    "stderr": str(e),
                    "exit": -1,
                    "background": False,
                }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": str(e),
                "exit": -1,
                "background": False,
            }

    def _infer_file_from_cmd(self, cmd: str) -> str:
        """Try to infer the primary file being executed from a command string."""
        parts = cmd.split()
        for part in parts:
            if part.endswith(".py"):
                return part
        for part in parts:
            if "." in part and not part.startswith("-"):
                candidate = part.split("/")[-1]
                if "." in candidate and len(candidate) < 100:
                    return candidate
        return ""

    async def _generate_file_content(self, path: str, purpose: str, plan: dict) -> str:
        """Generate file content from purpose description using LLM.

        Called when the planner provides purpose but not inline content.
        This separates planning (lightweight JSON) from code generation (pure text).
        """
        prompt = harness.FILE_CONTENT
        prompt = prompt.replace("{file_path}", path)
        prompt = prompt.replace("{purpose}", purpose)
        prompt = prompt.replace("{question}", self._current_question or "")
        prompt = prompt.replace("{hypotheses}", self._current_hypotheses or "（无）")
        prompt = prompt.replace("{plan_summary}", plan.get("round_rationale", "")[:500])
        try:
            resp = await self.llm.call(
                messages=[{"role": "user", "content": f"为文件 {path} 生成代码：{purpose}"}],
                system=prompt,
                temperature=getattr(self.config, "temperature", 0.3),
                max_tokens=getattr(self.config, "max_tokens", 4096),
            )
            code = resp.content.strip()
            if code.startswith("```"):
                idx = code.find("\n")
                code = code[idx+1:] if idx >= 0 else code[3:]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()
            log.info("practice.file_content_generated", path=path, size=len(code))
            return code
        except Exception as e:
            log.error("practice.file_content_error", path=path, error=str(e))
            return ""

    async def _fix_code(self, file_path: str, original_code: str,
                        exit_code: int, stderr: str) -> dict:
        """Use LLM to fix broken code."""
        prompt = (harness.CODE_FIX
                  .replace("{file_path}", file_path)
                  .replace("{original_code}", original_code)
                  .replace("{exit_code}", str(exit_code))
                  .replace("{stderr}", stderr[:2000]))
        response = await self.llm.call(
            messages=[{"role": "user", "content": "请修复代码。"}],
            system=prompt,
            temperature=getattr(self.config, "temperature", 0.3),
            max_tokens=getattr(self.config, "max_tokens", 4096),
        )
        result = self._parse_json_safe(response.content, {})
        if not result.get("fixed_content"):
            result["fixed_content"] = original_code
            result["fix_summary"] = "无法修复"
            result["unfixable"] = True
        return result

    async def _simulated_practice(
        self, question: str, decision: DecisionReport, trace: CognitiveTrace,
    ) -> PracticeReport:
        """No workspace fallback."""
        system = load_phase_prompt("practice", _PRACTICE_PROMPT)
        temperature = getattr(self.config, "temperature", 0.4)
        max_tokens = getattr(self.config, "max_tokens", 2048)

        facts_text = ""
        if trace.investigation:
            facts_text = "\n".join(
                f"- {f.content[:100]}" for f in trace.investigation.facts[:5]
            )
        contradiction_text = ""
        if trace.contradictions and trace.contradictions.principal_contradiction:
            contradiction_text = (
                trace.contradictions.principal_contradiction.description[:200]
            )
        action_text = "\n".join(
            f"{i+1}. {a.description}"
            for i, a in enumerate(decision.action_items[:6])
        ) or "（无）"

        resp = await self.llm.call(
            messages=[{"role": "user", "content": f"""
原始问题：{question}

调查发现：{facts_text or '（无）'}

主要矛盾：{contradiction_text or '（未识别）'}

决策方案：{decision.strategic_assessment[:400]}

行动项：{action_text}

请设计多轮实践实验来检验上述结论。注意实践不是一次性运行脚本——设计递进的实验序列。
"""}],
            system=system, temperature=temperature, max_tokens=max_tokens,
        )
        content = resp.content
        return PracticeReport(
            mode="epistemic_only",
            confidence_ceiling="V2",
            steps_taken=[PracticeStep(description=content[:600])],
            observed_outcomes=[],
            unexpected_findings=[],
            practice_summary=content[:800],
            success_indicators=[],
            failure_indicators=[],
        )

    # ── Dangerous commands blocked in practice phase ──
    # Practice should test hypotheses by running self-written scripts,
    # not reconfigure the environment or interact with the outside world.
    _BLOCKED_COMMAND_PATTERNS = [
        "pip install", "pip3 install", "pip uninstall",
        "sudo ", "su ",
        "curl ", "wget ", "fetch ",
        "git clone", "git push",
        "ssh ", "scp ", "rsync ",
        "npm install -g", "npm i -g",
        "apt", "apt-get", "yum", "dnf", "brew",
        "rm -rf /", "rm -r /",
        "chmod 777",
        "shutdown", "reboot", "poweroff",
        "docker run", "docker rm",
        "systemctl", "service ",
        "mount ", "umount ",
    ]

    # relaxed 模式下从黑名单移除的模式（允许 pip 安装与联网取数）
    _RELAXED_UNBLOCK = {
        "pip install", "pip3 install", "pip uninstall",
        "curl ", "wget ", "fetch ",
    }

    def _effective_blocked_patterns(self):
        """按 practice_sandbox_level 返回生效的命令黑名单。

        strict：完整黑名单（禁网、禁 pip）。
        relaxed：移除 pip/联网相关，但保留 rm -rf/ 、sudo、shutdown 等真正危险命令。
        """
        from ..config import settings
        level = getattr(settings, "practice_sandbox_level", "relaxed")
        if level == "relaxed":
            return [p for p in self._BLOCKED_COMMAND_PATTERNS
                    if p not in self._RELAXED_UNBLOCK]
        return self._BLOCKED_COMMAND_PATTERNS

    # ── Boundary mode ─────────────────────────────────────────

    def _parse_json_safe(self, raw: str, default=None):
        """Parse LLM JSON output, handling code fences and truncation."""
        if default is None:
            default = {}
        raw = raw.strip()
        while raw.startswith("```"):
            idx = raw.find("\n")
            raw = raw[idx+1:] if idx >= 0 else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip().rstrip("`")
        for prefix in ["json\n", "json"]:
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                break
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            for suffix in ['}', '}]}', ']}]}', '}]}]}']:
                try:
                    return json.loads(raw + suffix)
                except json.JSONDecodeError:
                    continue
            log.warning("practice.json_parse_error", raw=raw[:200])
            return default
