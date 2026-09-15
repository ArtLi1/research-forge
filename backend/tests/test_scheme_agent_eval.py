from app.evals.scheme_agent_eval import SchemeAgentEvalCase, evaluate_scheme_agent


def test_scheme_agent_eval_metrics() -> None:
    result = evaluate_scheme_agent(
        [
            SchemeAgentEvalCase(
                candidate_count=3,
                retrieved_scenario_count=4,
                retrieved_algorithm_count=3,
                constraint_passed=True,
                diversity_passed=True,
                goal_alignment_passed=True,
                retry_count=1,
            ),
            SchemeAgentEvalCase(
                candidate_count=2,
                retrieved_scenario_count=0,
                retrieved_algorithm_count=2,
                constraint_passed=False,
                diversity_passed=False,
                goal_alignment_passed=False,
                retry_count=0,
            ),
        ]
    )
    assert result.generation_success_rate == 0.5
    assert result.constraint_pass_rate == 0.5
    assert result.diversity_pass_rate == 0.5
    assert result.goal_alignment_rate == 0.5
    assert result.retrieval_success_rate == 0.5
    assert result.average_retry_count == 0.5
