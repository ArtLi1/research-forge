# 任务

检查一个修订后的候选方案是否对齐研究目标、违反项目硬约束或明确排除项，以及场景与算法是否兼容。

# 规则

- 只输出 CandidateConstraintCheck，candidate_index 固定为 0。
- goal_alignment_passed 表示方案是否真正回答研究目标。
- compatibility_passed 表示场景假设、信息条件与算法机制是否可以共同成立，且技术思路没有明显不可行之处。
- hard_constraint_violations 只记录明确违反目标中“必须/不得”和项目 exclusions 的内容。
- compatibility_risks 记录机制依赖、场景假设、信息可用性或复杂度之间的冲突。
- 不新增或改写方案内容。
