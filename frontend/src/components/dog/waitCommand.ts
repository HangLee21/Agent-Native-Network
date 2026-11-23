/** Resolves when a dog command reaches a final state (its updates arrive as dog-command pushes). */
import type { DogCommand } from '@/api/dog'
import { useDogStore } from '@/stores/dog'

const OPEN = new Set(['sent', 'running'])

export function waitCommand(id: string, timeoutMs = 135000): Promise<DogCommand | null> {
  const store = useDogStore()
  const t0 = Date.now()
  return new Promise((resolve) => {
    const iv = window.setInterval(() => {
      const c = [...store.commands.s10, ...store.commands.lite3].find((x) => x.id === id)
      if (c && !OPEN.has(c.state)) {
        window.clearInterval(iv)
        resolve(c)
      } else if (Date.now() - t0 > timeoutMs) {
        window.clearInterval(iv)
        resolve(c ?? null)
      }
    }, 200)
  })
}
