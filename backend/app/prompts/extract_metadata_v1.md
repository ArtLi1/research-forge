# 任务

根据论文知识卡和证据填写一个用户定义的元数据字段。

# 规则

- 只返回 MetadataAutoFillResult。
- 没有充分证据时 value 为 null，并解释原因。
- evidence 必须引用输入中存在的 chunk_id 和原文 quote。
- 不得改变字段定义，不得输出定义范围外的枚举值。
