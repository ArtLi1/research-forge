import { describe, expect, it } from 'vitest'

import { statusTone } from '../src/utils/status'

describe('statusTone', () => {
  it('maps terminal statuses to visible tones', () => {
    expect(statusTone('completed')).toBe('success')
    expect(statusTone('partial')).toBe('warning')
    expect(statusTone('failed')).toBe('danger')
  })
})
