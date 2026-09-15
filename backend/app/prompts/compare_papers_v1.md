# 任务

比较 2 至 5 篇论文。只使用输入的场景知识与算法知识，不重新推测原文。

# 固定维度

应用场景、算法思路、核心机制、创新差异、适用条件。

# 规则

- 输出 ComparisonResult，五个维度均必须出现。
- 每个条目只包含 paper_id 和简洁 statement，不输出证据 ID。
- conclusion_type 只能是 explicit_difference、synthesis、unconfirmed。
- 知识不足时使用 unconfirmed，不得补写事实。
- 不输出完整公式、约束或算法代码。
