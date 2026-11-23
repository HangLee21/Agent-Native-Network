<script setup lang="ts">
/**
 * Settings (ui-design.md §2.4): a section list on the left (飞行安全 / 目标选择与 AI / 飞行记录与录像 /
 * 系统与接入) with the field-dependent values, and one section at a time on the right. The forms of all
 * sections are owned here so unsaved edits survive switching; each editable section saves in one request
 * through the sticky save bar.
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import SafetySection from '@/components/settings/SafetySection.vue'
import SystemSection from '@/components/settings/SystemSection.vue'
import DevicesSection from '@/components/settings/DevicesSection.vue'
import { useFleetStore } from '@/stores/fleet'
import SaveBar from '@/components/settings/SaveBar.vue'
import TargetSettingsCard from '@/components/target/TargetSettingsCard.vue'
import HistorySettingsCard from '@/components/history/HistorySettingsCard.vue'
import WatchSettingsCard from '@/components/settings/WatchSettingsCard.vue'
import DogNavSettingsCard from '@/components/settings/DogNavSettingsCard.vue'
import { useDog2Store } from '@/stores/dogv2'
import { useWatchSettings } from '@/components/settings/useWatchSettings'
import { SAFETY_FIELD_NAMES, useSafetySettings } from '@/components/settings/useSafetySettings'
import { TARGET_FIELD_NAMES, useTargetSettings } from '@/components/settings/useTargetSettings'
import { useHistorySettings } from '@/components/settings/useHistorySettings'
import '@/components/settings/settings.css'
import { t } from '@/i18n'

const safetyForm = useSafetySettings()
const targetForm = useTargetSettings()
const historyState = useHistorySettings()
const watchState = useWatchSettings()

const SECTIONS = ['safety', 'devices', 'dognav', 'target', 'history', 'watch', 'system'] as const
const fleet = useFleetStore()
/** Dogs that can navigate outdoors (docs/dog/ui-design.md 19.7): the "狗的导航" section is listed only when there is one. */
const dog2 = useDog2Store()
const navDogs = computed(() => dog2.dogs.filter((d) => !!d.navCapability))
onMounted(() => void dog2.refresh())
type Section = (typeof SECTIONS)[number]
const isSection = (v: unknown): v is Section => typeof v === 'string' && (SECTIONS as readonly string[]).includes(v)
const SECTION_KEY = 'uav.settings.section'

const route = useRoute()
const router = useRouter()

function remembered(): Section | null {
  try {
    const v = localStorage.getItem(SECTION_KEY)
    return isSection(v) ? v : null
  } catch {
    return null
  }
}
const section = computed<Section>(() => (isSection(route.query.section) ? route.query.section : remembered() ?? 'safety'))
const content = ref<HTMLElement | null>(null)

async function pick(s: Section, anchor?: string): Promise<void> {
  try {
    localStorage.setItem(SECTION_KEY, s)
  } catch {
    /* storage unavailable: the query parameter still selects the section */
  }
  const switching = s !== section.value
  if (route.query.section !== s) await router.replace({ query: { ...route.query, section: s } })
  await nextTick()
  const target = anchor ? document.getElementById(anchor) : null
  if (target) target.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  else if (switching && content.value) content.value.scrollTop = 0
}

const unsaved = (n: number) => (n ? t('{n} 项未保存', { n }) : t('未保存'))
const navItems = computed(() => [
  {
    key: 'safety' as const, icon: 'shield', label: t('飞行安全'), sub: t('限高 · 速度 · 安全区 · 校验策略'),
    badge: safetyForm.dirty ? unsaved(safetyForm.changed.length) : '', kind: 'warn',
  },
  {
    key: 'devices' as const, icon: 'drone', label: t('设备与两机安全'), sub: t('登记 · 启用 · 名称颜色 · 靠近与返航高度'),
    badge: fleet.pending.length ? t('{n} 台待启用', { n: fleet.pending.length }) : t('{n} 台', { n: fleet.enabled.length }), kind: fleet.pending.length ? 'warn' : '',
  },
  ...(navDogs.value.length ? [{
    key: 'dognav' as const, icon: 'route', label: t('狗的导航'), sub: t('避障 · 到达半径 · 档位 · 允许区域'),
    badge: t('{n} 只', { n: navDogs.value.length }), kind: '',
  }] : []),
  {
    key: 'target' as const, icon: 'crosshair', label: t('目标选择与 AI'), sub: t('激光 · 动作距离 · AI 模式 · 工作区'),
    badge: targetForm.dirty ? unsaved(targetForm.changed.length) : '', kind: 'warn',
  },
  {
    key: 'history' as const, icon: 'clock', label: t('记录与录像'), sub: t('记录状态 · 录像开关'),
    badge: historyState.status ? (historyState.status.video.recordingEnabled ? t('录像开') : t('录像关')) : '',
    kind: historyState.status?.video.recordingEnabled ? 'ok' : '',
  },
  {
    key: 'watch' as const, icon: 'eye', label: t('演示与监视台'), sub: t('只显示飞过的轨迹 · 视频顺序'),
    badge: watchState.value ? (watchState.value.hideRoute ? t('隐藏航线') : t('显示航线')) : '', kind: '',
  },
  { key: 'system' as const, icon: 'info', label: t('系统与接入'), sub: t('语言 · 系统信息 · 外部接口'), badge: '', kind: '' },
])

const LASER_SHORT = { UNKNOWN: t('未确认'), ELLIPSOID: t('椭球高'), MSL: t('海拔 + N') } as const
const fieldItems = computed(() => {
  const s = safetyForm
  const tf = targetForm.form
  const mark = (changed: boolean) => (changed ? t('（未保存）') : '')
  return [
    {
      label: t('高度参数校验策略'), section: 'safety' as const, anchor: 'settings-policy',
      value: (s.form.unknownHeightPolicy === 'DUAL_CHECK' ? t('双重校验') : t('按推断参考系（默认）')) + mark(s.changed.includes('unknownHeightPolicy')),
    },
    {
      label: t('安全区'), section: 'safety' as const, anchor: 'settings-zone',
      value: (s.zoneEnabled ? t('已启用 · {n} 个顶点', { n: s.zone.length }) : t('未启用')) + mark(s.changed.includes('safeZoneEnabled') || s.changed.includes('safeZone')),
    },
    {
      label: t('激光高度参考系'), section: 'target' as const, anchor: 'settings-laser',
      value: tf ? LASER_SHORT[tf.laserAltitudeReference] + mark(targetForm.changed.includes('laserAltitudeReference')) : '—',
    },
    {
      label: t('飞往激光目标'), section: 'target' as const, anchor: 'settings-laser',
      value: !tf ? '—' : (tf.laserFlyToEnabled ? t('开启') : tf.laserAltitudeReference === 'UNKNOWN' ? t('关闭（参考系是“未确认”时不能开）') : t('关闭'))
        + mark(targetForm.changed.includes('laserFlyToEnabled')),
    },
  ]
})

const HEADS: Record<Section, { title: string; desc: string; save: string }> = {
  safety: { title: t('飞行安全'), desc: t('作用于所有航线保存、同步和飞行指令。限高与速度、安全区和校验策略一起保存。'), save: 'PUT /api/v1/safety/config' },
  devices: { title: t('设备与两机安全'), desc: t('R-28、R-29、S-05、S-06。设备的名称、颜色、启用即改即存；两机安全设置单独保存。'), save: 'PATCH /api/v1/drones/{sn} · PUT /api/v1/safety/fleet' },
  dognav: { title: t('狗的导航'), desc: t('每只能户外导航的狗的默认值：自动避障、到达半径、速度档位、允许区域。每只狗单独保存，下一次开始导航起生效。'), save: 'PUT /api/v2/dogs/{id}/nav/settings' },
  target: { title: t('目标选择与 AI'), desc: t('R-24 ~ R-27 草案。作用于目标动作与 AI 自动模式；激光、动作距离、AI 模式和工作区一起保存。'), save: 'PUT /api/v1/targets/config' },
  history: { title: t('记录与录像'), desc: t('录像开关切换后立即保存，从飞机下一次起飞、狗下一段记录起生效。'), save: 'PUT /api/v1/history/settings' },
  watch: { title: t('演示与监视台'), desc: t('作用于监视台的实时和回放。切换后立即保存，所有正在打开监视台的屏幕一起生效。'), save: 'PUT /api/v1/monitor/settings' },
  system: { title: t('系统与接入'), desc: t('界面语言，以及系统信息与外部接口说明。语言只对这台电脑上的这个浏览器生效。'), save: t('语言保存在本浏览器') },
}
const head = computed(() => HEADS[section.value])

const safetyNames = computed(() => safetyForm.changed.map((k) => SAFETY_FIELD_NAMES[k]))
const targetNames = computed(() => targetForm.changed.map((k) => TARGET_FIELD_NAMES[k] ?? k))
</script>

<template>
  <div class="settings-page">
    <nav class="s-nav scroll" :aria-label="t('设置分类')">
      <div class="nav-list">
        <button v-for="n in navItems" :key="n.key" type="button" class="nav-item" :class="{ current: section === n.key }"
          :aria-current="section === n.key ? 'page' : undefined" :data-test="`settings-nav-${n.key}`" @click="pick(n.key)">
          <AppIcon :name="n.icon" class="nav-icon" />
          <span class="nav-text"><b>{{ n.label }}</b><span class="nav-sub">{{ n.sub }}</span></span>
          <span v-if="n.badge" class="s-badge" :class="n.kind">{{ n.badge }}</span>
        </button>
      </div>
      <div class="field-box" data-test="settings-field-items">
        <b>{{ t('外场前核对（{n}）', { n: fieldItems.length }) }}</b>
        <span class="field-box-desc">{{ t('高度校验策略和激光参考系已在外场确认；部署或重置数据库后看一眼这几项。') }}</span>
        <button v-for="fi in fieldItems" :key="fi.label" type="button" class="fi" @click="pick(fi.section, fi.anchor)">
          <span class="fi-label">{{ fi.label }}</span><span class="fi-value">{{ fi.value }}</span>
        </button>
      </div>
    </nav>

    <div ref="content" class="s-content scroll">
      <div class="s-inner">
        <header class="sec-head">
          <div class="sec-title">
            <h1>{{ head.title }}</h1>
            <p>{{ head.desc }}</p>
          </div>
          <span class="api-tag num">{{ head.save }}</span>
        </header>

        <SafetySection v-if="section === 'safety'" :model="safetyForm" />
        <TargetSettingsCard v-else-if="section === 'target'" :model="targetForm" />
        <HistorySettingsCard v-else-if="section === 'history'" :model="historyState" />
        <DevicesSection v-else-if="section === 'devices'" />
        <template v-else-if="section === 'dognav'">
          <DogNavSettingsCard v-for="d in navDogs" :key="d.id" :dog="d" />
          <p v-if="!navDogs.length" class="dim">{{ t('没有能户外导航的狗。') }}</p>
        </template>
        <WatchSettingsCard v-else-if="section === 'watch'" :model="watchState" />
        <SystemSection v-else />
      </div>

      <SaveBar v-if="section === 'safety' && safetyForm.dirty" :title="t('飞行安全')" :names="safetyNames" :save-label="t('保存安全设置')" save-test="save-safety"
        :dirty="safetyForm.dirty" :saving="safetyForm.saving" @reset="safetyForm.reset()" @save="safetyForm.save()" />
      <SaveBar v-else-if="section === 'target' && targetForm.dirty" :title="t('目标选择与 AI')" :names="targetNames" :save-label="t('保存目标选择设置')"
        save-test="save-target-settings" :dirty="targetForm.dirty" :saving="targetForm.saving" @reset="targetForm.reset()" @save="targetForm.save()" />
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  display: flex;
  height: 100%;
  min-height: 0;
}

/* ---------- section list ---------- */
.s-nav {
  flex: 0 0 272px;
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
  padding: var(--sp-4) var(--sp-3);
  border-right: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel) 55%, var(--bg));
}
.nav-list {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}
.nav-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.nav-item:hover {
  background: var(--panel-2);
}
.nav-item.current {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.nav-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.nav-icon {
  flex: none;
  margin-top: 1px;
  color: var(--text-dim);
}
.nav-item.current .nav-icon {
  color: var(--accent);
}
.nav-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.nav-text b {
  font-size: var(--fs-md);
}
.nav-sub {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.nav-item .s-badge {
  align-self: center;
}

.field-box {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border-radius: var(--r-panel);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border));
  background: color-mix(in srgb, var(--accent) 6%, transparent);
}
.field-box > b {
  font-size: var(--fs-sm);
  color: var(--text);
}
.field-box-desc {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.fi {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 6px 8px;
  border-radius: var(--r-ctl);
  border: 1px solid transparent;
  background: color-mix(in srgb, var(--panel-3) 45%, transparent);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.fi:hover {
  border-color: var(--warn);
}
.fi:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.fi-label {
  font-size: var(--fs-xs);
  font-weight: 600;
}
.fi-value {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}

/* ---------- content ---------- */
.s-content {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.s-inner {
  flex: 1 0 auto;
  width: 100%;
  max-width: 940px;
  margin: 0 auto;
  padding: var(--sp-5) var(--sp-5) var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}
.sec-head {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--sp-2) var(--sp-4);
}
.sec-title {
  flex: 1 1 360px;
  min-width: 0;
}
.sec-title h1 {
  font-size: 22px;
}
.sec-title p {
  margin: 4px 0 0;
  font-size: var(--fs-sm);
  color: var(--text-dim);
}
.api-tag {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  padding: 3px 8px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  white-space: nowrap;
}

/* narrow screens: the section list stacks above the content and the whole page scrolls */
@media (max-width: 760px) {
  .settings-page {
    flex-direction: column;
    overflow-y: auto;
  }
  .s-nav {
    flex: none;
    overflow: visible;
    border-right: 0;
    border-bottom: 1px solid var(--border);
  }
  .nav-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
  .nav-sub {
    display: none;
  }
  .s-content {
    flex: none;
    overflow: visible;
  }
  .s-inner {
    padding: var(--sp-4) var(--sp-4) var(--sp-5);
  }
}
</style>
