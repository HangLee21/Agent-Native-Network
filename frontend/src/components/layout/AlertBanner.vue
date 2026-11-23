<script setup lang="ts">
/**
 * Prominent alerts (ui-design.md §5, §2.7): critical = red, blinking icon, persistent; warning = amber.
 * Every drone's alerts, each prefixed with the drone's name; platform-level ones (disk, recording) once.
 * Two-drone proximity (S-05) comes from the fleet: the pair, and a resume button for each drone it paused.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { controlApi, type Alert } from '@/api/control'
import { useFleetStore } from '@/stores/fleet'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { time } from '@/utils/format'
import { t } from '@/i18n'

/** Alerts not about one drone: shown once, without a drone name. */
const PLATFORM_CODES = new Set(['VIDEO_DISK_LOW', 'PROXIMITY', 'PROXIMITY_BLIND'])

const fleet = useFleetStore()

interface Row {
  key: string
  sn: string | null
  label: string | null
  alert: Alert
}

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const seen = new Set<string>()
  const many = fleet.enabled.length > 1
  for (const d of fleet.enabled) {
    for (const a of useControlStore(d.gatewaySn).alerts) {
      if (a.code === 'PROXIMITY') continue // drawn from the fleet below
      if (PLATFORM_CODES.has(a.code)) {
        if (seen.has(a.code)) continue
        seen.add(a.code)
        out.push({ key: a.code, sn: null, label: null, alert: a })
      } else {
        out.push({ key: `${d.gatewaySn}:${a.code}`, sn: d.gatewaySn, label: many ? d.label : null, alert: a })
      }
    }
  }
  return out
})

/** Drones hovering at a waypoint set to wait for the operator (route PAUSED, reason WAYPOINT_CONFIRM, 2026-11-04). */
const waiting = computed(() =>
  fleet.enabled.flatMap((d) => {
    const e = useExecutionStore(d.gatewaySn).current
    return e?.active && e.state === 'PAUSED' && e.pauseReason === 'WAYPOINT_CONFIRM' ? [{ d, e }] : []
  }),
)

/** Drones the proximity monitor paused (route PAUSED, reason PROXIMITY): resumed only by the operator. */
const paused = computed(() =>
  fleet.enabled.filter((d) => {
    const e = useExecutionStore(d.gatewaySn).current
    return e?.state === 'PAUSED' && e.pauseReason === 'PROXIMITY'
  }),
)

function pairText(p: (typeof fleet.proximity)[number]): string {
  const v = p.verticalM == null ? t('高度差未知') : t('高度差 {n} m', { n: Math.round(p.verticalM) })
  const stopping = p.stopping?.length ? t('，正在让 {names} 悬停（还在移动）', { names: p.stopping.join(t('、')) }) : ''
  const stopped = p.stopped.length ? t('，已让 {names} 悬停', { names: p.stopped.join(t('、')) }) : ''
  const stale = p.stale?.length ? t('（{names} 已 {n} 秒没有位置数据，按最后位置判断）', { names: p.stale.join(t('、')), n: p.staleSeconds ?? 0 }) : ''
  return t('{a} 与 {b}：水平 {h} m · {v}{stale}{stopping}{stopped}', { a: p.aLabel, b: p.bLabel, h: Math.round(p.horizontalM), v, stale, stopping, stopped })
}

const returnHome = (sn: string) => useControlStore(sn).run('rth', t('一键返航'), () => controlApi(sn).returnHome())
const resume = (sn: string) => useExecutionStore(sn).resume()
</script>

<template>
  <div v-if="rows.length || fleet.proximity.length || paused.length || waiting.length" class="alerts" role="alert" data-test="alerts">
    <div v-for="p in fleet.proximity" :key="`${p.a}|${p.b}`" class="alert" :class="p.level === 'hold' ? 'critical' : 'warning'"
         data-code="PROXIMITY">
      <AppIcon name="alert" :size="18" class="icon" />
      <b>{{ t('两机靠近') }}</b>
      <span class="msg">{{ pairText(p) }}</span>
      <span class="t num">{{ time(p.since) }}</span>
    </div>
    <div v-for="d in paused" :key="`paused:${d.gatewaySn}`" class="alert warning" data-code="PROXIMITY_PAUSED">
      <AppIcon name="stop" :size="18" class="icon" />
      <b>{{ t('{name} 航线已暂停', { name: d.label }) }}</b>
      <span class="msg">{{ t('因两机靠近，平台让 {name} 悬停；拉开距离后由操作员恢复', { name: d.label }) }}</span>
      <button class="btn btn-sm" data-test="resume" @click="resume(d.gatewaySn)">
        <AppIcon name="play" :size="15" />{{ t('继续 {name} 的航线', { name: d.label }) }}
      </button>
    </div>
    <div v-for="x in waiting" :key="`wait:${x.d.gatewaySn}`" class="alert info" data-code="WAYPOINT_CONFIRM">
      <AppIcon name="clock" :size="18" class="icon" />
      <b>{{ fleet.enabled.length > 1 ? t('{name} 等你确认', { name: x.d.label }) : t('等你确认') }}</b>
      <span class="msg">{{ x.e.message }}</span>
      <button class="btn btn-sm" data-test="confirm-continue" @click="resume(x.d.gatewaySn)">
        <AppIcon name="play" :size="15" />{{ fleet.enabled.length > 1 ? t('确认，继续 {name} 的航线', { name: x.d.label }) : t('确认，继续航线') }}
      </button>
    </div>
    <div v-for="r in rows" :key="r.key" class="alert" :class="r.alert.level === 'CRITICAL' ? 'critical' : 'warning'" :data-code="r.alert.code">
      <AppIcon name="alert" :size="18" class="icon" />
      <b><span v-if="r.label" class="who">{{ r.label }}</span>{{ r.alert.title }}</b>
      <span class="msg">{{ r.alert.message }}</span>
      <span class="t num">{{ time(r.alert.since) }}</span>
      <button v-if="r.alert.suggestion === 'RETURN_HOME' && r.sn" class="btn btn-sm btn-warn" @click="returnHome(r.sn)">
        <AppIcon name="home" :size="15" />{{ r.label ? t('让 {name} 返航', { name: r.label }) : t('建议返航') }}
      </button>
      <span v-else-if="r.alert.suggestion" class="sugg">{{ r.alert.suggestion }}</span>
    </div>
  </div>
</template>

<style scoped>
.alerts {
  flex: none;
  position: relative;
  z-index: 1500;
  display: flex;
  flex-direction: column;
}
.alert {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 38px;
  padding: 4px var(--sp-4);
  font-size: var(--fs-sm);
  border-bottom: 1px solid rgba(0, 0, 0, 0.3);
}
.critical {
  background: color-mix(in srgb, var(--danger) 88%, #000);
  color: #fff;
}
.critical .icon {
  animation: blink 1s steps(1) infinite;
}
.warning {
  background: color-mix(in srgb, var(--warn) 85%, #000);
  color: #111;
}
.info {
  background: color-mix(in srgb, var(--accent) 80%, #000);
  color: #fff;
}
.who {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.25);
  font-weight: 700;
}
.msg {
  flex: 1;
  min-width: 0;
}
.t {
  opacity: 0.8;
  font-size: var(--fs-xs);
}
.sugg {
  font-size: var(--fs-xs);
  opacity: 0.9;
}
.alert .btn {
  color: #111;
  background: #fff;
  border-color: #fff;
}
</style>
