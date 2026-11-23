<script setup lang="ts">
/**
 * Dangerous landings (R-13, ui-design.md §5): emergency landing and force landing live in a
 * collapsed "危险操作" block. The buttons work only after an explicit 30 s unlock, still ask for
 * confirmation, and the block re-locks after an action or when the unlock expires.
 */
import { onBeforeUnmount, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import CommandStatus from './CommandStatus.vue'
import { controlApi, type CommandRecord } from '@/api/control'
import { useControlStore } from '@/stores/control'
import { useConfirmStore } from '@/stores/confirm'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

/** `bare`: body only, always open — used inside the monitor footer's 降落 popover, which is the toggle. */
const props = withDefaults(defineProps<{ enabled: boolean; unlockSeconds?: number; bare?: boolean }>(), { unlockSeconds: 30, bare: false })

const control = useControlStore()
const confirm = useConfirmStore()
const open = ref(false)
const remaining = ref(0)
let timer: ReturnType<typeof setInterval> | null = null

function lock(): void {
  remaining.value = 0
  if (timer) clearInterval(timer)
  timer = null
}

function unlock(): void {
  lock()
  remaining.value = props.unlockSeconds
  timer = setInterval(() => {
    remaining.value -= 1
    if (remaining.value <= 0) lock()
  }, 1000)
}

const toggleLock = () => (remaining.value > 0 ? lock() : unlock())

async function run(label: string, msg: string, call: () => Promise<CommandRecord>): Promise<void> {
  if (remaining.value <= 0) return
  const ok = await confirm.ask({ title: label, message: msg, confirmText: label, danger: true, focus: 'cancel' })
  lock()
  if (!ok) return
  await control.run('landing', label, call)
}

const emergencyLanding = () => run(t('紧急降落'), t('飞行器将原地降落到地面，请确认下方安全。'), () => controlApi(sn).emergencyLanding())
const forceLanding = () => run(t('强制降落'), t('强制降落会直接降落到地面，请谨慎使用。'), () => controlApi(sn).forceLanding())

onBeforeUnmount(lock)
</script>

<template>
  <div class="danger-zone" :class="{ bare }" data-test="danger-zone">
    <button v-if="!bare" class="dz-head" :aria-expanded="open" data-test="danger-toggle" @click="open = !open; if (!open) lock()">
      <AppIcon :name="open ? 'down' : 'chevron'" :size="16" /><AppIcon name="alert" :size="15" />{{ t('危险操作') }}
    </button>
    <div v-if="open || bare" class="dz-body">
      <p class="note">{{ t('紧急降落、强制降落会让飞行器直接降落到地面（需 DRC、需在空中）。先解锁，{n} 秒内有效，用完或到时自动上锁。', { n: unlockSeconds }) }}</p>
      <button class="btn btn-sm" :class="remaining > 0 ? 'btn-warn' : 'btn-ghost'" :disabled="!enabled" data-test="danger-unlock" @click="toggleLock">
        <AppIcon :name="remaining > 0 ? 'lock-open' : 'lock'" :size="15" />{{ remaining > 0 ? t('已解锁 · {n} 秒后上锁（点击上锁）', { n: remaining }) : t('解锁 30 秒') }}
      </button>
      <div class="btns">
        <button class="btn btn-sm btn-danger" :disabled="!enabled || remaining <= 0" data-test="emergency-landing" @click="emergencyLanding"><AppIcon name="land" :size="15" />{{ t('紧急降落') }}</button>
        <button class="btn btn-sm btn-danger" :disabled="!enabled || remaining <= 0" data-test="force-landing" @click="forceLanding"><AppIcon name="land" :size="15" />{{ t('强制降落') }}</button>
      </div>
      <CommandStatus :record="control.byAction('landing')" />
    </div>
  </div>
</template>

<style scoped>
.danger-zone {
  border: 1px solid color-mix(in srgb, var(--danger) 45%, transparent);
  border-radius: var(--r-ctl);
}
.danger-zone.bare {
  border: none;
}
.dz-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px var(--sp-2);
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border: none;
  color: var(--danger);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.dz-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--sp-2);
  padding: var(--sp-2);
}
.btns {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.note {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
