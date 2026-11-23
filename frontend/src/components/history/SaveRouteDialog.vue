<script setup lang="ts">
/** Save a flown track as a new route; the backend thins it and runs the same safety check as any route. */
import { ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { ApiError } from '@/api/http'
import { historyApi } from '@/api/history'
import type { Route } from '@/api/routes'
import { t } from '@/i18n'

const props = defineProps<{ sessionId: string; defaultName: string }>()
const emit = defineEmits<{ (e: 'saved', r: Route): void; (e: 'cancel'): void }>()

const name = ref(props.defaultName)
const spacing = ref(20)
const busy = ref(false)
const error = ref<string | null>(null)
const violations = ref<{ message: string; waypointIndex: number | null }[]>([])

async function save(): Promise<void> {
  busy.value = true
  error.value = null
  violations.value = []
  try {
    emit('saved', await historyApi.saveRoute(props.sessionId, { name: name.value, spacingMeters: spacing.value }))
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('保存失败')
    if (e instanceof ApiError && e.status === 422) {
      violations.value = (e.details as { details?: { violations?: { message: string; waypointIndex: number | null }[] } })?.details?.violations ?? []
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="backdrop" @click.self="emit('cancel')">
    <div class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('存为航线')">
      <div class="panel-head"><span>{{ t('把实际航迹存为航线') }}</span></div>
      <div class="panel-body">
        <label class="field"><span>{{ t('航线名称') }}</span><input v-model="name" class="input" maxlength="200" data-test="save-route-name" /></label>
        <label class="field"><span>{{ t('航点间距（m）') }}</span><input v-model.number="spacing" class="input" type="number" min="5" max="2000" step="5" /></label>
        <p class="dim hint">{{ t('每隔约 {n} m 取一个航点，高度取相对起飞点高度；低于平台最低高度的起飞爬升和降落段不纳入。保存时与其他航线一样经过安全校验。', { n: spacing }) }}</p>
        <p v-if="error" class="err"><AppIcon name="alert" :size="15" />{{ error }}</p>
        <ul v-if="violations.length" class="violations">
          <li v-for="(v, i) in violations" :key="i">{{ v.waypointIndex != null ? t('航点 {n}：', { n: v.waypointIndex + 1 }) : '' }}{{ v.message }}</li>
        </ul>
      </div>
      <div class="actions">
        <button class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button class="btn btn-primary" :disabled="busy || !name.trim()" data-test="save-route-confirm" @click="save">
          <AppIcon :name="busy ? 'spinner' : 'save'" />{{ t('保存到航线库') }}
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
  z-index: 2400;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 460px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
.panel-body {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
}
.hint {
  margin: 0;
  font-size: var(--fs-sm);
}
.violations {
  margin: 0;
  padding-left: 18px;
  color: var(--danger);
  font-size: var(--fs-sm);
}
.err {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--danger);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4);
  border-top: 1px solid var(--border);
}
</style>
