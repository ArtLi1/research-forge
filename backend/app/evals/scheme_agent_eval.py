from pydantic import BaseModel, Field


class SchemeAgentEvalCase(BaseModel):
    candidate_count: int = Field(ge=0)
    retrieved_scenario_count: int = Field(ge=0)
    retrieved_algorithm_count: int = Field(ge=0)
    constraint_passed: bool
    diversity_passed: bool
    goal_alignment_passed: bool
    retry_count: int = Field(ge=0)


class SchemeAgentEvalResult(BaseModel):
    generation_success_rate: float
    constraint_pass_rate: float
    diversity_pass_rate: float
    goal_alignment_rate: float
    retrieval_success_rate: float
    average_retry_count: float


def evaluate_scheme_agent(cases: list[SchemeAgentEvalCase]) -> SchemeAgentEvalResult:
    if not cases:
        return SchemeAgentEvalResult(
            generation_success_rate=0,
            constraint_pass_rate=0,
            diversity_pass_rate=0,
            goal_alignment_rate=0,
            retrieval_success_rate=0,
            average_retry_count=0,
        )
    count = len(cases)
    return SchemeAgentEvalResult(
        generation_success_rate=sum(case.candidate_count == 3 for case in cases) / count,
        constraint_pass_rate=sum(case.constraint_passed for case in cases) / count,
        diversity_pass_rate=sum(case.diversity_passed for case in cases) / count,
        goal_alignment_rate=sum(case.goal_alignment_passed for case in cases) / count,
        retrieval_success_rate=sum(
            case.retrieved_scenario_count > 0 and case.retrieved_algorithm_count > 0
            for case in cases
        )
        / count,
        average_retry_count=sum(case.retry_count for case in cases) / count,
    )
