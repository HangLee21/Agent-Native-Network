<script setup lang="ts">
/**
 * One dog's navigation defaults (docs/dog/ui-design.md 19.7; PUT /api/v2/dogs/{id}/nav/settings): avoidance default,
 * arrival radius (within the range the dog reports), default speed level (only the levels the dog reports), the
 * allowed area (drawn like the safe zone: click adds, drag moves, right-click deletes), whether the aircraft safe zone
 * stands in when no area is set, and how far the first point may be from the dog. Saved with its own button.
 */
import { computed, onMounted, reactive, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import FleetLayers from '@/components/map/FleetLayers.vue'
import ZoneEditLayer from '@/components/map/ZoneEditLayer.vue'
import { useDog2Store } from '@/stores/dogv2'
import { NAV_SETTINGS_DEFAULT, type Dog2, type Dog2NavSettings } from '@/api/dogv2'
import { speedLabel, speedLevels } from '@/components/dog/dogNav'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = defineProps<{ dog: Dog2 }>()
const v2 = useDog2Store()
const cap = computed(() => props.dog.navCapability ?? null)
const levels = computed(() => speedLevels(cap.value))
const range = computed<[number, number]>(() => {
  const r = cap.value?.arrive_radius_m
  return Array.isArray(r) && r.length === 2 ? [r[0], r[1]] : [0.5, 50]
})

const form = reactive({ ...NAV_SETTINGS_DEFAULT, area: [] as LatLon[] })
const saved = ref<Dog2NavSettings | null>(null)
const loading = ref(true)
const saving = ref(false)
const drawing = ref(false)
const msg = ref<{ cls: string; text: string } | null>(null)

function fill(s: Dog2NavSettings): void {
  saved.value = s
  form.avoidanceDefault = s.avoidanceDefault
  form.arriveRadiusM = s.arriveRadiusM
  form.speedLevel = s.speedLevel
  form.useAircraftZone = s.useAircraftZone
  form.maxFirstM = s.maxFirstM
  form.area = (s.area ?? []).map(([lat, lon]) => ({ lat, lon }))
}

function current(): Dog2NavSettings {
  return {
    avoidanceDefault: form.avoidanceDefault, arriveRadiusM: Number(form.arriveRadiusM), speedLevel: form.speedLevel || null,
    area: form.area.length >= 3 ? form.area.map((p) => [p.lat, p.lon] as [number, number]) : null,
    useAircraftZone: form.useAircraftZone, maxFirstM: Number(form.maxFirstM),
  }
}
const dirty = computed(() => !!saved.value && JSON.stringify(current()) !== JSON.stringify(saved.value))
const why = computed(() => {
  const r = Number(form.arriveRadiusM)
  if (!Number.isFinite(r) || r < range.value[0] || r > range.value[1]) return t('到达半径要在 {a}–{b} m 之间', { a: range.value[0], b: range.value[1] })
  const m = Number(form.maxFirstM)
  if (!Number.isFinite(m) || m <= 0) return t('第一个点离狗的上限要大于 0')
  if (form.area.length > 0 && form.area.length < 3) return t('允许区域至少 3 个顶点')
  return null
})

onMounted(async () => {
  const v = await v2.navLoad(props.dog.id)
  loading.value = false
  fill(v?.settings ?? NAV_SETTINGS_DEFAULT)
})

async function save(): Promise<void> {
  if (why.value) return
  saving.value = true
  const r = await v2.navSaveSettings(props.dog.id, current())
  saving.value = false
  if (typeof r === 'string') msg.value = { cls: 'bad', text: t('没保存：{why}', { why: r }) }
  else {
    fill(r)
    drawing.value = false
    msg.value = { cls: 'ok', text: t('已保存') }
  }
}

function onMapClick(p: LatLon): void {
  if (drawing.value) form.area = [...form.area, p]
}
const center = computed<LatLon | null>(() => {
  const p = props.dog.position
  if (p?.lat != null && p.lon != null) return { lat: p.lat, lon: p.lon }
  return form.area[0] ?? null
})
</script>

<template>
  <section class="panel s-card" :data-test="`dog-nav-settings-${dog.id}`">
    <div class="s-card-head">
      <h2>{{ t('{name} · 导航默认值', { name: dog.label }) }}</h2>
      <span v-if="dirty" class="s-badge warn">{{ t('未保存') }}</span>
      <button class="btn btn-sm" :disabled="!dirty || saving" @click="saved && fill(saved)">{{ t('还原') }}</button>
      <button class="btn btn-sm btn-primary" :disabled="!dirty || saving || !!why" :title="why ?? ''" data-test="dog-nav-save" @click="save">
        <AppIcon name="save" :size="14" />{{ t('保存') }}
      </button>
    </div>
    <p v-if="loading" class="s-note">{{ t('正在读取…') }}</p>
    <div class="s-grid">
      <label class="sw">
        <input v-model="form.avoidanceDefault" type="checkbox" role="switch" :disabled="cap?.avoidance === false" data-test="dog-nav-avoid-default" />
        <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
        <span>{{ t('自动避障默认开') }}</span>
      </label>
      <label class="field s-field">
        <span class="s-label">{{ t('到达半径') }}</span>
        <span class="s-input-row"><input v-model.number="form.arriveRadiusM" class="input num s-num" type="number" :min="range[0]" :max="range[1]" step="0.5" data-test="dog-nav-radius" /><span class="s-unit">m</span></span>
        <span class="s-hint">{{ t('{a}–{b} m（狗报的范围）；不要小于 GPS 的实际误差', { a: range[0], b: range[1] }) }}</span>
      </label>
      <label v-if="levels.length" class="field s-field">
        <span class="s-label">{{ t('默认档位') }}</span>
        <select v-model="form.speedLevel" class="input" data-test="dog-nav-speed">
          <option :value="null">{{ t('狗的默认档') }}</option>
          <option v-for="l in levels" :key="l.id" :value="l.id">{{ speedLabel(l) }}</option>
        </select>
      </label>
      <label class="field s-field">
        <span class="s-label">{{ t('第一个点离狗的上限') }}</span>
        <span class="s-input-row"><input v-model.number="form.maxFirstM" class="input num s-num" type="number" min="1" data-test="dog-nav-maxfirst" /><span class="s-unit">m</span></span>
      </label>
    </div>

    <div class="s-card-head">
      <h3 class="s-sub">{{ t('允许区域') }}</h3>
      <label class="sw">
        <input v-model="form.useAircraftZone" type="checkbox" role="switch" data-test="dog-nav-aircraft-zone" />
        <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
        <span>{{ t('没设区域时用飞机安全区') }}</span>
      </label>
      <button class="btn btn-sm" :class="{ 'btn-primary': drawing }" data-test="dog-nav-draw" @click="drawing = !drawing"><AppIcon name="edit" :size="15" />{{ drawing ? t('完成绘制') : t('绘制 / 编辑') }}</button>
      <button class="btn btn-sm" :disabled="form.area.length === 0" @click="form.area = []"><AppIcon name="trash" :size="15" />{{ t('清空') }}</button>
    </div>
    <div class="s-map" :class="{ drawing }">
      <MapCanvas :center="center" :zoom="17" @map-click="onMapClick">
        <ZoneEditLayer :points="form.area" @move="(i, p) => (form.area = form.area.map((q, j) => (j === i ? p : q)))" @remove="(i) => (form.area = form.area.filter((_, j) => j !== i))" />
        <FleetLayers markers-only />
      </MapCanvas>
      <span v-if="drawing" class="s-map-chip">{{ t('绘制中：单击地图添加顶点，拖动调整，右键删除。当前 {n} 个顶点。', { n: form.area.length }) }}</span>
    </div>
    <p class="s-note">
      {{ form.area.length >= 3 ? t('这只狗的所有点和每一段都要在这个区域里，平台和狗各查一遍。') : form.useAircraftZone ? t('没设区域：飞机安全区开着时用它；都没有时只限第一个点离狗的距离。') : t('没设区域：只限第一个点离狗的距离。') }}
    </p>
    <p v-if="why" class="s-warn-line">{{ why }}</p>
    <p v-if="msg" class="s-note" :class="msg.cls === 'bad' ? 'bad' : 'ok'" data-test="dog-nav-msg">{{ msg.text }}</p>
  </section>
</template>

<style scoped>
.bad { color: var(--danger); }
.ok { color: var(--ok); }
</style>
