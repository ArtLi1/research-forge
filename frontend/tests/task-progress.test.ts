import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'

import { useTaskProgress } from '../src/composables/useTaskProgress'

class FakeEventSource extends EventTarget {
  static connections: FakeEventSource[] = []
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    super()
    FakeEventSource.connections.push(this)
  }
  send(name: string, id = 'first') {
    this.dispatchEvent(new MessageEvent(name, { data: JSON.stringify({ id, status: name }) }))
  }
}

const scopes: ReturnType<typeof effectScope>[] = []
function setup() {
  const id = ref('first')
  const completed = vi.fn()
  const scope = effectScope()
  scopes.push(scope)
  const progress = scope.run(() => useTaskProgress(() => id.value, completed))!
  return { id, completed, scope, progress }
}

beforeEach(() => {
  FakeEventSource.connections = []
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => {
  scopes.splice(0).forEach((scope) => scope.stop())
  vi.unstubAllGlobals()
})

it.each(['completed', 'failed', 'cancelled'])('closes on %s', (event) => {
  const { completed, progress } = setup()
  const connection = FakeEventSource.connections[0]!
  connection.send(event)
  expect(connection.close).toHaveBeenCalledOnce()
  expect(progress.task.value?.id).toBe('first')
  expect(completed).toHaveBeenCalledTimes(event === 'completed' ? 1 : 0)
  connection.send('progress', 'stale')
  expect(progress.task.value?.id).toBe('first')
})

it('switches tasks and ignores late events from the previous connection', async () => {
  const { id, scope, progress } = setup()
  const first = FakeEventSource.connections[0]!
  id.value = 'second'
  await nextTick()
  expect(first.close).toHaveBeenCalledOnce()
  const second = FakeEventSource.connections[1]!
  expect(second.url).toContain('/second/events')
  second.send('progress', 'second')
  first.send('progress', 'stale')
  expect(progress.task.value?.id).toBe('second')
  scope.stop()
  expect(second.close).toHaveBeenCalledOnce()
})

it('follows a retry and reports reconnection state', () => {
  const { progress } = setup()
  progress.followTask('replacement')
  expect(progress.activeTaskId.value).toBe('replacement')
  const connection = FakeEventSource.connections[1]!
  connection.onerror!()
  expect(progress.disconnected.value).toBe(true)
  connection.onopen!()
  expect(progress.disconnected.value).toBe(false)
})
