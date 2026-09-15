from app.agents.scheme_agent import SchemeAgent

# Compatibility import for callers written before the Agent boundary was explicit.
SchemeGenerationGraph = SchemeAgent

__all__ = ["SchemeAgent", "SchemeGenerationGraph"]
