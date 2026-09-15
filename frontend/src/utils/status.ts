export const statusLabel: Record<string, string> = {
  uploaded: '已上传',
  queued: '排队中',
  parsing: '解析中',
  chunking: '分块中',
  embedding: '向量化',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败',
}

export function statusTone(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'completed' || status === 'succeeded') return 'success'
  if (status === 'partial') return 'warning'
  if (status === 'failed') return 'danger'
  return 'info'
}
