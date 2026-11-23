import { defineStore } from 'pinia'
import { ref } from 'vue'

/** Confirmation dialog for dangerous actions (ui-design.md §5). */
export interface ConfirmRequest {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
  /** Which button gets initial focus: "cancel" for destructive actions, "confirm" for quick safety actions. */
  focus?: 'confirm' | 'cancel'
  details?: string[]
}

export const useConfirmStore = defineStore('confirm', () => {
  const current = ref<ConfirmRequest | null>(null)
  let resolver: ((ok: boolean) => void) | null = null

  function ask(req: ConfirmRequest): Promise<boolean> {
    resolver?.(false)
    current.value = req
    return new Promise((resolve) => (resolver = resolve))
  }

  function answer(ok: boolean): void {
    resolver?.(ok)
    resolver = null
    current.value = null
  }

  return { current, ask, answer }
})
