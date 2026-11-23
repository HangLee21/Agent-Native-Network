<script setup lang="ts">
/** Import waypoints from a file (R-17): preview (format, points, warnings, safety) before saving. */
import { ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { importRouteFile, type ImportResult } from '@/api/importer'
import { ApiError } from '@/api/http'
import { violationsOf } from '@/api/safety'
import { t } from '@/i18n'

const emit = defineEmits<{ (e: 'done', routeId: string): void; (e: 'cancel'): void }>()
const file = ref<File | null>(null)
const name = ref('')
const defaultHeight = ref<number | null>(60)
const takeoffAltitude = ref<number | null>(null)
const preview = ref<ImportResult | null>(null)
const error = ref<string | null>(null)
const busy = ref(false)

function pick(e: Event): void {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null
  preview.value = null
  error.value = null
}

function errText(e: unknown): string {
  if (!(e instanceof ApiError)) return t('请求失败')
  const v = violationsOf(e.details)
  return v.length ? t('{head}：{list}', { head: e.message, list: v.map((x) => x.message).join(t('；')) }) : e.message
}

async function run(dryRun: boolean): Promise<void> {
  if (!file.value) return
  busy.value = true
  error.value = null
  try {
    const r = await importRouteFile(file.value, { name: name.value || undefined, defaultHeight: defaultHeight.value, takeoffAltitude: takeoffAltitude.value, dryRun })
    if (dryRun) preview.value = r
    else if (r.saved) emit('done', r.saved.id)
  } catch (e) {
    error.value = errText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="backdrop">
    <div class="dialog panel" role="dialog" aria-modal="true" :aria-label="t('导入航线文件')">
      <div class="panel-head"><span class="row"><AppIcon name="upload" />{{ t('导入航线文件') }}</span></div>
      <div class="panel-body">
        <label class="drop">
          <input type="file" accept=".kmz,.geojson,.json,.csv,.txt" data-test="import-file" @change="pick" />
          <AppIcon name="file" :size="22" />
          <span>{{ file ? file.name : t('选择文件：DJI 航线 KMZ（WPML）、GeoJSON、CSV') }}</span>
        </label>
        <div class="grid">
          <label class="field"><span>{{ t('航线名称（留空使用文件中的名称）') }}</span><input v-model="name" class="input" /></label>
          <label class="field"><span>{{ t('默认高度（m，点缺少高度时使用）') }}</span><input v-model.number="defaultHeight" class="input num" type="number" /></label>
          <label class="field wide"><span>{{ t('起飞点高度（仅当文件使用 EGM96 / 椭球高时需要，用于换算为相对起飞点高度）') }}</span>
            <input v-model.number="takeoffAltitude" class="input num" type="number" :placeholder="t('可留空')" /></label>
        </div>
        <p class="note">{{ t('CSV 列：lat, lon, height[, speed][, hover][, actions]，可带表头（支持中文列名）；GeoJSON 坐标为 [经度, 纬度, 高度]。导入的航线与手绘航线使用同一模型并经过同一安全检查。') }}</p>
        <div v-if="error" class="bad"><AppIcon name="alert" :size="16" />{{ error }}</div>
        <div v-if="preview" class="preview" data-test="import-preview">
          <div><b>{{ preview.format }}</b> · {{ t('{n} 个航点 · 名称「{name}」', { n: preview.route.waypoints.length, name: preview.route.name }) }}</div>
          <ul v-if="preview.warnings.length" class="warns">
            <li v-for="w in preview.warnings" :key="w">{{ w }}</li>
          </ul>
          <div :class="preview.safety.passed ? 'ok' : 'bad'">
            <AppIcon :name="preview.safety.passed ? 'shield' : 'alert'" :size="16" />
            {{ preview.safety.passed ? t('安全检查通过') : t('安全检查未通过：{list}', { list: preview.safety.violations.map((v) => v.message).join(t('；')) }) }}
          </div>
        </div>
      </div>
      <div class="actions">
        <button class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button class="btn" :disabled="!file || busy" data-test="import-preview-btn" @click="run(true)"><AppIcon name="eye" />{{ t('预览') }}</button>
        <button class="btn btn-primary" :disabled="!file || busy || preview?.safety.passed === false" data-test="import-confirm" @click="run(false)">
          <AppIcon :name="busy ? 'spinner' : 'upload'" />{{ t('导入') }}
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
  width: 600px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow);
}
.drop {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-4);
  border: 1px dashed var(--border);
  border-radius: var(--r-panel);
  cursor: pointer;
  color: var(--text-dim);
}
.drop input {
  position: absolute;
  opacity: 0;
  width: 1px;
}
.drop:hover {
  border-color: var(--accent);
  color: var(--text);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
  margin-top: var(--sp-3);
}
.grid .input {
  width: 100%;
}
.wide {
  grid-column: 1 / -1;
}
.note {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.preview {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--sp-3);
  border-radius: var(--r-ctl);
  background: var(--panel-2);
  font-size: var(--fs-sm);
}
.warns {
  margin: 0;
  padding-left: 18px;
  color: var(--warn);
  font-size: var(--fs-xs);
}
.ok {
  color: var(--ok);
  display: flex;
  gap: 6px;
}
.bad {
  color: var(--danger);
  display: flex;
  gap: 6px;
  font-size: var(--fs-sm);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
</style>
