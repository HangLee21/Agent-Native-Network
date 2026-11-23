<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useConfirmStore } from '@/stores/confirm'
import { t } from '@/i18n'

const c = useConfirmStore()
const okBtn = ref<HTMLButtonElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)

watch(
  () => c.current,
  async (req) => {
    if (!req) return
    await nextTick()
    ;(req.focus === 'confirm' ? okBtn.value : cancelBtn.value)?.focus()
  },
)

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    // this Esc only cancels the dialog: it must not also reach window-level shortcuts (e.g. the dog pad's "stop")
    e.preventDefault()
    e.stopPropagation()
    c.answer(false)
  }
}
</script>

<template>
  <div v-if="c.current" class="backdrop" @keydown="onKey">
    <div class="dialog panel" role="alertdialog" aria-modal="true" :aria-label="c.current.title">
      <div class="panel-head">{{ c.current.title }}</div>
      <div class="panel-body">
        <p class="msg">{{ c.current.message }}</p>
        <ul v-if="c.current.details?.length" class="details">
          <li v-for="d in c.current.details" :key="d">{{ d }}</li>
        </ul>
      </div>
      <div class="actions">
        <button ref="cancelBtn" class="btn" data-test="confirm-cancel" @click="c.answer(false)">{{ c.current.cancelText ?? t('取消') }}</button>
        <button ref="okBtn" class="btn" :class="c.current.danger ? 'btn-danger' : 'btn-primary'" data-test="confirm-ok" @click="c.answer(true)">
          {{ c.current.confirmText ?? t('确认') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2500;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 440px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
.msg {
  margin: 0;
}
.details {
  margin: var(--sp-3) 0 0;
  padding-left: 18px;
  color: var(--text-dim);
  font-size: var(--fs-sm);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
</style>
