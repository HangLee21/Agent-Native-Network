import { defineStore } from 'pinia'
import { ref } from 'vue'

export type ToastKind = 'ok' | 'warn' | 'danger' | 'info'

export interface ToastAction {
  label: string
  /** Router path opened when the action is clicked. */
  to: string
}

export interface Toast {
  id: number
  kind: ToastKind
  text: string
  action?: ToastAction
}

export const useToastStore = defineStore('toast', () => {
  const items = ref<Toast[]>([])
  let seq = 0

  function push(kind: ToastKind, text: string, ms = 4000, action?: ToastAction): void {
    const id = ++seq
    items.value.push(action ? { id, kind, text, action } : { id, kind, text })
    window.setTimeout(() => dismiss(id), ms)
  }

  function dismiss(id: number): void {
    items.value = items.value.filter((t) => t.id !== id)
  }

  return { items, push, dismiss }
})
