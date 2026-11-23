<script setup lang="ts">
/**
 * Route editor panel (R-06): name, global parameters, waypoint list edited in place, the selected waypoint's details.
 * 2026-11-04 (dual-drone planning): height / speed / hover are edited in the row; checked rows are edited together;
 * changing a default can be applied to existing waypoints; another saved route can be appended ("接上另一条航线").
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import WaypointForm from './WaypointForm.vue'
import ChainRouteDialog from './ChainRouteDialog.vue'
import OverlayPicker from './OverlayPicker.vue'
import { FINISH_LABELS, RC_LOST_LABELS, type Waypoint } from '@/api/routes'
import { useEditorStore } from '@/stores/editor'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import { meters } from '@/utils/format'
import { t, tc } from '@/i18n'

const props = defineProps<{ invalid?: Set<number> }>()
const emit = defineEmits<{ (e: 'open-library'): void }>()
const ed = useEditorStore()
const confirm = useConfirmStore()
const toast = useToastStore()
const showGlobals = ref(false)
const showChain = ref(false)

const n = computed(() => ed.draft?.waypoints.length ?? 0)
const allChecked = computed(() => n.value > 0 && ed.checked.length === n.value)
const someChecked = computed(() => ed.checked.length > 0 && !allChecked.value)

function onKey(e: KeyboardEvent): void {
  const target = e.target as HTMLElement
  if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return
  if ((e.key === 'Delete' || e.key === 'Backspace') && ed.selected !== null) {
    ed.removePoint(ed.selected)
    e.preventDefault()
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function value(e: Event): string {
  return (e.target as HTMLInputElement).value.trim()
}

/** A row cell changed: this waypoint, or every checked one when it is checked among others. */
function edit(i: number, field: 'relativeHeight' | 'speed' | 'hoverSeconds', e: Event): void {
  const raw = value(e)
  let patch: Partial<Waypoint>
  if (field === 'speed') {
    patch = { speed: raw === '' ? null : Number(raw) } // empty = follow the default speed
  } else if (raw === '' || !Number.isFinite(Number(raw))) {
    // height and hover cannot be empty: put the old value back
    ;(e.target as HTMLInputElement).value = String(ed.draft!.waypoints[i]![field])
    return
  } else {
    patch = field === 'hoverSeconds' ? { hoverSeconds: Math.max(0, Number(raw)) } : { relativeHeight: Number(raw) }
  }
  const count = ed.setField(i, patch)
  if (count > 1) toast.push('ok', t('已同时修改选中的 {n} 个航点', { n: count }))
}

function check(i: number, e: MouseEvent): void {
  ed.toggleCheck(i, e.shiftKey)
}

async function defaultHeightChanged(): Promise<void> {
  const d = ed.draft!
  ed.touch()
  const h = d.defaultHeight
  const differ = d.waypoints.filter((w) => w.relativeHeight !== h).length
  if (!differ || !Number.isFinite(h)) return
  const ok = await confirm.ask({
    title: t('现有航点也改吗？'),
    message: t('默认高度只用于以后新加的航点。现有 {n} 个航点的高度和 {h} m 不同，要把全部航点都改成 {h} m 吗？', { n: differ, h }),
    confirmText: t('全部改成 {h} m', { h }),
    cancelText: t('只用于新航点'),
    focus: 'cancel',
  })
  if (ok) ed.applyToAll({ relativeHeight: h })
}

async function defaultSpeedChanged(): Promise<void> {
  const d = ed.draft!
  ed.touch()
  const own = d.waypoints.filter((w) => w.speed !== null && w.speed !== d.defaultSpeed).length
  if (!own || !Number.isFinite(d.defaultSpeed)) return
  const ok = await confirm.ask({
    title: t('单独设了速度的航点也改吗？'),
    message: t('没单独设速度的航点会自动用 {speed} m/s。另有 {n} 个航点单独设了速度，要让它们也改用 {speed} m/s 吗？', { speed: d.defaultSpeed, n: own }),
    confirmText: t('全部改用默认速度'),
    cancelText: t('保留单独的速度'),
    focus: 'cancel',
  })
  if (ok) ed.applyToAll({ speed: null })
}

async function removeChecked(): Promise<void> {
  const c = ed.checked.length
  if (await confirm.ask({ title: t('删除选中的航点'), message: t('确认删除选中的 {n} 个航点？', { n: c }), confirmText: t('删除'), danger: true, focus: 'cancel' })) {
    ed.removeChecked()
  }
}

function chained(text: string): void {
  showChain.value = false
  toast.push('ok', text, 5000)
}
</script>

<template>
  <div class="route-editor" data-test="route-editor">
    <template v-if="ed.draft">
      <!-- Everything above the buttons scrolls as one; the buttons stay pinned so they can always be reached. -->
      <div class="body scroll" data-test="editor-body">
        <div class="head">
          <input v-model="ed.draft.name" class="input name" :placeholder="t('航线名称（必填）')" data-test="route-name" @input="ed.touch()" />
          <span class="state dim">{{ ed.dirty ? t('未保存') : ed.draft.id ? t('已保存 · v{version}', { version: ed.draft.version }) : t('新航线') }}</span>
        </div>
        <div class="hint">
          <AppIcon name="crosshair" :size="15" />
          {{ t('单击地图添加航点，拖动调整；右键或 Delete 删除选中航点') }}
        </div>
        <div class="stats num">
          <span><b>{{ n }}</b> {{ t('{n|个航点|个航点}', { n }) }}</span>
          <span>{{ t('总长') }} <b>{{ meters(ed.length) }}</b></span>
          <span>{{ t('最高') }} <b>{{ ed.maxHeight }}</b> m</span>
        </div>

        <button class="globals-toggle" :aria-expanded="showGlobals" data-test="globals-toggle" @click="showGlobals = !showGlobals">
          <span class="t"><AppIcon :name="showGlobals ? 'down' : 'chevron'" :size="16" />{{ t('全局参数') }}</span>
          <span class="dim num">{{ t('默认 {h} m · {s} m/s · 返航高度 {rth} m · 完成后{finish}', { h: ed.draft.defaultHeight, s: ed.draft.defaultSpeed, rth: ed.rthEffective ?? '—', finish: FINISH_LABELS[ed.draft.finishAction] }) }}</span>
        </button>
        <div v-if="showGlobals" class="globals" data-test="globals">
          <label class="field"><span>{{ t('默认高度 (m，新航点用)') }}</span>
            <input v-model.number="ed.draft.defaultHeight" class="input num" type="number" data-test="default-height" @change="defaultHeightChanged" /></label>
          <label class="field"><span>{{ t('默认速度 (m/s)') }}</span>
            <input v-model.number="ed.draft.defaultSpeed" class="input num" type="number" step="0.5" data-test="route-speed" @change="defaultSpeedChanged" /></label>
          <label class="field" :title="t('起飞后先垂直升到这个高度，再飞向第一个航点')"><span>{{ t('起飞先升到 (m)') }}</span>
            <input v-model.number="ed.draft.takeoffSecurityHeight" class="input num" type="number" @change="ed.touch()" /></label>
          <div class="field">
            <span>{{ t('返航高度 (m)') }}</span>
            <div class="rth">
              <select v-model="ed.draft.rthHeightAuto" class="input" data-test="rth-mode" :aria-label="t('返航高度方式')" @change="ed.touch()">
                <option :value="true">{{ t('自动') }}</option>
                <option :value="false">{{ t('手动') }}</option>
              </select>
              <span v-if="ed.draft.rthHeightAuto" class="auto num" data-test="rth-auto">{{ ed.rthEffective ?? '—' }}</span>
              <input v-else v-model.number="ed.draft.rthHeight" class="input num" type="number" data-test="rth-height" @change="ed.touch()" />
            </div>
          </div>
          <p class="note">
            {{ t('返航高度：飞机自己返航时用（航线结束返航、遥控器失联、低电量、中途按返航），比这个高度低时会先爬升到它再飞回。 “自动”= 最后一个航点的高度。两架同时飞时返航高度要错开，起飞前平台会检查。') }}
          </p>
          <label class="field"><span>{{ t('航线结束动作') }}</span>
            <select v-model="ed.draft.finishAction" class="input" @change="ed.touch()">
              <option v-for="(l, k) in FINISH_LABELS" :key="k" :value="k">{{ l }}</option>
            </select></label>
          <label class="field"><span>{{ t('遥控器失联动作') }}</span>
            <select v-model="ed.draft.rcLostAction" class="input" @change="ed.touch()">
              <option v-for="(l, k) in RC_LOST_LABELS" :key="k" :value="k">{{ l }}</option>
            </select></label>
          <p class="note">{{ t('所有高度都从起飞点的地面算起（起飞点地面 = 0 m）。平台执行时，低于 20 m 的航点飞机会先爬升到 20 m（大疆限制）。') }}</p>
        </div>

        <OverlayPicker />
        <div v-if="n" class="cols" data-test="waypoint-columns">
          <input type="checkbox" class="chk" :checked="allChecked" :indeterminate="someChecked" :aria-label="t('全选航点')" data-test="check-all"
                 @change="ed.setAllChecked(!allChecked)" />
          <span class="c-idx">#</span>
          <span class="c-h" :title="t('从起飞点的地面算起')">{{ t('高度 m') }}</span>
          <span class="c-s" :title="t('空 = 用默认速度')">{{ t('速度 m/s') }}</span>
          <span class="c-hv">{{ t('悬停 s') }}</span>
        </div>
        <div v-if="ed.checked.length" class="batch" data-test="batch-bar">
          <span class="grow">{{ t('已选 {n} 个', { n: ed.checked.length }) }}<span v-if="ed.checked.length > 1">{{ t('，改其中任一行会一起改') }}</span></span>
          <button class="btn btn-ghost btn-sm" :title="t('取消选择')" @click="ed.setAllChecked(false)">{{ tc('deselect', '取消') }}</button>
          <button class="btn btn-ghost btn-sm danger" :title="t('删除选中的航点')" data-test="remove-checked" @click="removeChecked">{{ t('删除') }}</button>
        </div>
        <div class="list scroll" data-test="waypoint-list">
          <EmptyState v-if="n === 0" icon="crosshair" :title="t('单击地图添加第一个航点')" />
          <div
            v-for="(w, i) in ed.draft.waypoints"
            :key="i"
            class="wp"
            :class="{ selected: ed.selected === i, checked: ed.isChecked(i), invalid: props.invalid?.has(i) }"
            @click="ed.selected = i"
          >
            <input type="checkbox" class="chk" :checked="ed.isChecked(i)" :aria-label="t('选中航点 {n}', { n: i + 1 })" data-test="wp-check"
                   @click.stop="check(i, $event)" />
            <span class="idx num">{{ i + 1 }}</span>
            <input class="cell c-h num" type="number" step="1" :value="w.relativeHeight" :aria-label="t('航点 {n} 高度', { n: i + 1 })" data-test="wp-height"
                   @focus="ed.selected = i" @change="edit(i, 'relativeHeight', $event)" />
            <input class="cell c-s num" type="number" step="0.5" min="0" :value="w.speed ?? ''" :placeholder="String(ed.draft.defaultSpeed)"
                   :aria-label="t('航点 {n} 速度', { n: i + 1 })" data-test="wp-speed" @focus="ed.selected = i" @change="edit(i, 'speed', $event)" />
            <input class="cell c-hv num" type="number" step="1" min="0" :value="w.hoverSeconds" :aria-label="t('航点 {n} 悬停秒数', { n: i + 1 })"
                   data-test="wp-hover" @focus="ed.selected = i" @change="edit(i, 'hoverSeconds', $event)" />
            <span class="badges">
              <span v-if="w.waitForConfirm" class="wait" :title="t('到达后悬停，等你确认再飞下一点')" data-test="wp-wait-badge"><AppIcon name="clock" :size="14" /></span>
              <span v-if="w.actions.some((a) => a.type === 'TAKE_PHOTO')" :title="t('到点拍照')"><AppIcon name="camera" :size="14" /></span>
              <span v-if="w.actions.some((a) => a.type === 'START_RECORD')" :title="t('到点开始录像')"><AppIcon name="record" :size="14" /></span>
            </span>
            <button class="btn btn-ghost btn-sm mini" :title="t('删除航点 {n}', { n: i + 1 })" @click.stop="ed.removePoint(i)"><AppIcon name="trash" :size="14" /></button>
          </div>
        </div>
        <div v-if="n" class="chain-row">
          <button class="btn btn-sm grow" data-test="open-chain" @click="showChain = true"><AppIcon name="link" :size="15" />{{ t('接上另一条航线') }}</button>
        </div>
        <WaypointForm v-if="ed.selected !== null" :index="ed.selected" />
      </div>
      <div class="footer">
        <slot name="checks" />
        <slot name="footer" />
      </div>
      <ChainRouteDialog v-if="showChain" @done="chained" @cancel="showChain = false" />
    </template>
    <EmptyState v-else icon="map" :title="t('当前没有打开的航线')" :hint="t('新建航线后在地图上单击选点；也可以从航线列表打开已保存的航线。')">
      <button class="btn btn-primary" data-test="new-route" @click="ed.startNew()"><AppIcon name="plus" />{{ t('新建航线') }}</button>
      <button class="btn" @click="emit('open-library')"><AppIcon name="library" />{{ t('航线列表') }}</button>
    </EmptyState>
  </div>
</template>

<style scoped>
.route-editor {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
.body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.body > * {
  flex: none;
}
.head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-4) var(--sp-2);
}
.name {
  flex: 1;
  font-size: var(--fs-lg);
  font-weight: 600;
}
.state {
  font-size: var(--fs-xs);
  white-space: nowrap;
}
.hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 var(--sp-4);
  padding: 6px var(--sp-2);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--accent) 10%, transparent);
  color: var(--text-dim);
  font-size: var(--fs-xs);
}
.stats {
  display: flex;
  gap: var(--sp-4);
  padding: var(--sp-2) var(--sp-4);
  font-size: var(--fs-sm);
  color: var(--text-dim);
}
.stats b {
  color: var(--text);
}
.globals-toggle {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  margin: 0 var(--sp-4);
  padding: 6px 0;
  background: none;
  border: none;
  border-top: 1px solid var(--border);
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.globals-toggle .t {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* the summary gets its own line and wraps: nothing is cut off in the narrow panel */
.globals-toggle .dim {
  font-weight: 400;
  font-size: var(--fs-xs);
  padding-left: 22px;
}
.globals {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--sp-2) var(--sp-3);
  padding: var(--sp-2) var(--sp-4) var(--sp-3);
}
.globals .input {
  width: 100%;
  min-width: 0;
}
.rth {
  display: flex;
  gap: 6px;
  align-items: center;
}
.rth select {
  width: 76px !important;
  flex: none;
}
.rth .auto {
  flex: 1;
  min-height: 36px;
  display: flex;
  align-items: center;
  padding: 0 var(--sp-2);
  border-radius: var(--r-ctl);
  background: var(--panel-2);
}
.note {
  grid-column: 1 / -1;
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.cols,
.wp {
  display: grid;
  grid-template-columns: 16px 24px 54px 54px 46px minmax(0, 1fr) 26px;
  align-items: center;
  gap: 5px;
  padding: 3px var(--sp-2) 3px var(--sp-3);
}
.cols {
  border-top: 1px solid var(--border);
  font-size: var(--fs-xs);
  color: var(--text-dim);
  padding-top: 6px;
  padding-bottom: 4px;
}
.cols .c-idx {
  text-align: center;
}
.batch {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 var(--sp-2) 4px;
  padding: 2px 4px 2px var(--sp-2);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-size: var(--fs-xs);
}
.batch .btn {
  flex: none;
  white-space: nowrap;
  min-height: 26px;
  padding: 0 8px;
}
.batch .danger {
  color: var(--danger);
}
/* A long list scrolls on its own so the selected waypoint's form stays close; the whole body scrolls as well. */
.list {
  max-height: min(50vh, 440px);
  border-top: 1px solid var(--border);
}
.wp {
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: var(--fs-sm);
}
.wp:hover {
  background: var(--panel-2);
}
.wp.checked {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.wp.selected {
  background: color-mix(in srgb, var(--accent) 16%, transparent);
}
.chk {
  accent-color: var(--accent);
  margin: 0;
}
.cell {
  width: 100%;
  min-width: 0;
  height: 28px;
  padding: 0 6px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font: inherit;
  text-align: right;
}
.cell:focus {
  outline: none;
  border-color: var(--accent);
}
.cell::placeholder {
  color: var(--text-dim);
}
.idx {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--accent-ink);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
}
.wp.selected .idx {
  background: #facc15;
  color: #0d1117;
}
.wp.invalid .idx {
  background: var(--danger);
  color: #fff;
}
.wp.invalid.selected .idx {
  box-shadow: 0 0 0 2px #facc15;
}
.badges {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
  color: var(--text-dim);
}
.badges > span {
  display: flex;
}
.badges .wait {
  color: var(--warn);
}
.mini {
  width: 26px;
  min-width: 26px;
  padding: 0;
  justify-content: center;
}
.chain-row {
  display: flex;
  padding: var(--sp-2) var(--sp-4);
}
.footer {
  flex: none;
  border-top: 1px solid var(--border);
  padding: var(--sp-3) var(--sp-4);
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
}
.footer:empty {
  display: none;
}
</style>
