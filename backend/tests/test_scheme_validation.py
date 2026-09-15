import pytest
from pydantic import ValidationError

from app.schemas.scheme import CandidateSchemeContent, CandidateSet
from app.services.scheme_validation import schemes_are_diverse


def _candidate(name: str, route: str) -> CandidateSchemeContent:
    return CandidateSchemeContent(
        name=name,
        core_research_question=[f"{route} research statement"],
        scenario_innovation=[f"{route} scenario"],
        model_level_changes=[f"{route} model"],
        algorithm_innovation=[f"{route} algorithm"],
        possible_paper_contributions=[f"{route} contribution"],
        borrowed_mechanisms=[f"{route} mechanism"],
        expected_advantages=[f"{route} advantage"],
        combination_rationale=[f"{route} rationale"],
        required_assumptions=[f"{route} assumption"],
        simple_combination_risk="May be a simple combination.",
        novelty_risk="Novelty requires validation.",
        compatibility_risks=[],
        implementation_complexity="medium",
        recommendation_score=4,
        unresolved_questions=["How robust is the route?"],
    )


def test_candidate_set_requires_exactly_three_distinct_names() -> None:
    with pytest.raises(ValidationError):
        CandidateSet(
            candidates=[
                _candidate("same", "route-a"),
                _candidate("same", "route-b"),
                _candidate("third", "route-c"),
            ]
        )


def test_diversity_gate_uses_scheme_content() -> None:
    candidates = [
        _candidate("UAV relay route", "multi-hop UAV"),
        _candidate("Semantic split route", "semantic task split"),
        _candidate("Market route", "distributed matching"),
    ]
    assert schemes_are_diverse(candidates)
