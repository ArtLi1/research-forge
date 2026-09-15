# 任务

逐个检查三个候选方案是否对齐研究目标、违反项目硬约束或明确排除项，以及场景与算法机制是否兼容。

# 规则

- 只输出 CandidateConstraintSet，candidate_index 必须覆盖 0、1、2。
- goal_alignment_passed 仅在方案确实回答了研究目标时为 true。
- compatibility_passed 仅在场景假设、信息条件与算法机制可以共同成立，且技术思路没有明显不可行之处时为 true。
- hard_constraint_violations 只记录明确违反目标中“必须/不得”和项目 exclusions 的内容。
- compatibility_risks 记录机制依赖、场景假设、信息可用性或复杂度之间的冲突。
- 不新增方案内容，不把一般风险夸大成硬约束违规。
