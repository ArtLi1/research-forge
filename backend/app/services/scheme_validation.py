import json
from difflib import SequenceMatcher
from typing import Any

from app.providers.chat import ChatModelProvider, load_prompt
from app.schemas.scheme import (
    CandidateConstraintSet,
    CandidateSchemeContent,
    SchemeRiskAssessment,
    SchemeValidationResult,
)


def schemes_are_diverse(candidates: list[CandidateSchemeContent]) -> bool:
    signatures = [
        " | ".join(
            [
                *item.core_research_question,
                *item.scenario_innovation,
                *item.model_level_changes,
                *item.algorithm_innovation,
            ]
        ).casefold()
        for item in candidates
    ]
    return all(
        SequenceMatcher(None, signatures[left], signatures[right]).ratio() < 0.84
        for left in range(len(signatures))
        for right in range(left + 1, len(signatures))
    )


def build_risk_assessment(
    candidate: CandidateSchemeContent,
    *,
    diversity_passed: bool,
    goal_alignment_passed: bool,
    compatibility_passed: bool,
    hard_constraint_violations: list[str],
    compatibility_risks: list[str],
) -> SchemeRiskAssessment:
    return SchemeRiskAssessment(
        diversity_passed=diversity_passed,
        goal_alignment_passed=goal_alignment_passed,
        compatibility_passed=compatibility_passed,
        hard_constraint_violations=hard_constraint_violations,
        compatibility_risks=list(
            dict.fromkeys([*candidate.compatibility_risks, *compatibility_risks])
        ),
        remaining_risks=list(
            dict.fromkeys(
                [
                    candidate.simple_combination_risk,
                    candidate.novelty_risk,
                    *candidate.unresolved_questions,
                ]
            )
        ),
    )


class SchemeValidator:
    def __init__(self, chat: ChatModelProvider) -> None:
        self.chat = chat

    async def validate(
        self,
        *,
        candidates: list[CandidateSchemeContent],
        goal: str,
        project_context: dict[str, Any],
    ) -> SchemeValidationResult:
        diversity_passed = schemes_are_diverse(candidates)
        semantic = await self.chat.generate_structured(
            [
                {
                    "role": "system",
                    "content": load_prompt(
                        "check_scheme_constraints_v1.md", offloading_guidance=True
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "project_context": project_context,
                            "candidates": [item.model_dump(mode="json") for item in candidates],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            CandidateConstraintSet,
            temperature=0,
        )
        checks = sorted(semantic.checks, key=lambda item: item.candidate_index)
        goal_alignment_passed = all(item.goal_alignment_passed for item in checks)
        compatibility_passed = all(item.compatibility_passed for item in checks)
        constraint_passed = not any(item.hard_constraint_violations for item in checks)
        feedback: list[str] = []
        if not diversity_passed:
            feedback.append("三个候选方案结构过于相似；改变核心场景、模型或算法路线。")
        for check in checks:
            if not check.goal_alignment_passed:
                feedback.append(f"候选 {check.candidate_index + 1} 与研究目标对齐不足。")
            if not check.compatibility_passed:
                feedback.append(f"候选 {check.candidate_index + 1} 的场景与算法不兼容。")
            for violation in check.hard_constraint_violations:
                feedback.append(f"候选 {check.candidate_index + 1} 违反硬约束：{violation}")
            for risk in check.compatibility_risks:
                feedback.append(f"候选 {check.candidate_index + 1} 兼容性风险：{risk}")
        return SchemeValidationResult(
            passed=(
                diversity_passed
                and goal_alignment_passed
                and constraint_passed
                and compatibility_passed
            ),
            diversity_passed=diversity_passed,
            goal_alignment_passed=goal_alignment_passed,
            constraint_passed=constraint_passed,
            compatibility_passed=compatibility_passed,
            feedback=feedback,
            candidates=candidates,
            constraint_checks=checks,
        )
