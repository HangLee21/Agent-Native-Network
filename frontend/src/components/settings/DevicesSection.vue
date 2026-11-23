<script setup lang="ts">
/**
 * 设备与两机安全 section of the settings page (R-28, R-29, S-05, S-06; ui-design.md 2.7). Devices: every RC that
 * connected registers itself; here it gets a name and colour and is enabled — only enabled devices accept
 * commands. Two-drone safety: what happens when two drones come close, the thresholds, and the minimum
 * return-height separation. Each change saves at once (one request), disabling an airborne drone asks first.
 */
import { reactive, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { DeviceView, FleetSafetyConfig } from '@/api/drones'
import { ApiError } from '@/api/http'
import { useFleetStore } from '@/stores/fleet'
import { useTelemetryStore } from '@/stores/telemetry'
import { useConfirmStore } from '@/stores/confirm'
import { useToastStore } from '@/stores/toast'
import { time } from '@/utils/format'
import { t } from '@/i18n'

const fleet = useFleetStore()
const confirm = useConfirmStore()
const toast = useToastStore()

const names = reactive<Record<string, string>>({})
watch(() => fleet.drones, (list) => {
  for (const d of list) if (names[d.gatewaySn] === undefined) names[d.gatewaySn] = d.label
}, { immediate: true })

async function save(d: DeviceView, u: Parameters<typeof fleet.update>[1]): Promise<void> {
  try {
    await fleet.update(d.gatewaySn, u)
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('保存失败'))
  }
}

async function toggle(d: DeviceView): Promise<void> {
  if (d.enabled) {
    const airborne = useTelemetryStore(d.gatewaySn).airborne
    const ok = await confirm.ask({
      title: t('停用 {name}', { name: d.label }),
      message: airborne
        ? t('{name} 正在空中。停用时平台先停下它正在执行的航线、飞往、环绕、目标动作和 AI（飞机悬停），再释放控制权，之后由飞手在遥控器上操作。停用后平台只接受返航、急停、降落和停止类指令。确认停用？', { name: d.label })
        : t('停用后平台不再给 {name} 发普通指令（返航、急停、降落和停止类指令仍可用），但仍显示它的位置和状态。', { name: d.label }),
      confirmText: t('停用'), danger: airborne, focus: 'cancel',
    })
    if (!ok) return
  }
  await save(d, { enabled: !d.enabled })
}

function rename(d: DeviceView): void {
  const v = (names[d.gatewaySn] ?? '').trim()
  if (v && v !== d.label) void save(d, { label: v })
  else names[d.gatewaySn] = d.label
}

// ------------------------------------------------------------------ two-drone safety

const form = ref<FleetSafetyConfig | null>(null)
watch(() => fleet.safety, (c) => (form.value = c ? { ...c } : null), { immediate: true })
const saving = ref(false)

async function saveSafety(): Promise<void> {
  if (!form.value) return
  saving.value = true
  try {
    const { updatedAt: _ignored, ...u } = form.value
    await fleet.updateSafety(u)
    toast.push('ok', t('两机安全设置已保存'))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('保存失败'))
  } finally {
    saving.value = false
  }
}
const changed = () => !!form.value && !!fleet.safety && JSON.stringify(form.value) !== JSON.stringify(fleet.safety)
</script>

<template>
  <section class="panel s-card" aria-labelledby="settings-devices-title">
    <div class="s-card-head"><h2 id="settings-devices-title">{{ t('设备') }}</h2></div>
    <p class="s-card-desc">
      {{ t('遥控器第一次接入（在 Pilot 2 打开接入页并连接）就会自动登记在这里，默认不启用。启用后平台才会给它发指令；未启用的设备仍显示位置和状态。不需要改配置，也不需要重启。') }}
    </p>
    <p v-if="!fleet.drones.length" class="s-note">{{ t('还没有设备接入。') }}</p>
    <table v-else class="devices" data-test="devices">
      <thead>
        <tr><th>{{ t('名称') }}</th><th>{{ t('颜色') }}</th><th>{{ t('遥控器 SN') }}</th><th>{{ t('飞行器') }}</th><th>{{ t('状态') }}</th><th>{{ t('最近上线') }}</th><th>{{ t('启用') }}</th></tr>
      </thead>
      <tbody>
        <tr v-for="d in fleet.drones" :key="d.gatewaySn" :class="{ off: !d.enabled }" :data-sn="d.gatewaySn">
          <td>
            <input v-model="names[d.gatewaySn]" class="input name" maxlength="16" :aria-label="t('{name} 的名称', { name: d.label })"
                   @change="rename(d)" @keydown.enter="rename(d)" />
          </td>
          <td><input type="color" class="color" :value="d.color" :aria-label="t('{name} 的颜色', { name: d.label })" @change="save(d, { color: ($event.target as HTMLInputElement).value })" /></td>
          <td class="num">{{ d.gatewaySn }}</td>
          <td class="num">{{ d.droneSn ?? '—' }}<span v-if="d.model" class="dim"> · {{ d.model }}</span><span v-if="d.simulated" class="tag">{{ t('模拟') }}</span></td>
          <td>
            <span class="chip" :class="d.online && d.droneOnline ? 'ok' : d.online ? 'warn' : 'danger'"><span class="dot" />
              {{ d.online ? (d.droneOnline ? t('在线') : t('遥控器在线 · 飞行器未连接')) : t('离线') }}</span>
          </td>
          <td class="num dim">{{ d.lastSeenAt ? time(d.lastSeenAt) : '—' }}</td>
          <td>
            <button class="btn btn-sm" :class="d.enabled ? '' : 'btn-primary'" :data-test="`device-toggle-${d.gatewaySn}`" @click="toggle(d)">
              {{ d.enabled ? t('停用') : t('启用') }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </section>

  <section v-if="form" class="panel s-card" aria-labelledby="settings-fleet-title">
    <div class="s-card-head"><h2 id="settings-fleet-title">{{ t('两机安全') }}</h2></div>
    <p class="s-card-desc">
      {{ t('两架同时在空中时，平台每秒判断 5 次是否靠近：位置和高度都往前推算 {n} 秒，同一时刻水平距离小于「基础距离 + 接近速度 × 反应时间」并且高度差小于高度阈值，就算靠近（飞到另一架正上方再下降也算）。只在两架都在空中、都不在起降阶段时判断。阈值要在外场测出刹车距离后再调。', { n: form.proximityLookaheadS }) }}
    </p>
    <div class="s-grid wide">
      <fieldset class="s-field mode" data-test="proximity-mode">
        <legend class="s-label">{{ t('靠近时') }}</legend>
        <label><input v-model="form.proximityMode" type="radio" value="HOLD" /> {{ t('报警并悬停：只停平台正在驱动、并且在移动（水平移动或升降）的那架（航线暂停、结束飞往、退出环绕、停目标动作和 AI）；返航中、飞手手动在飞的只报警。悬停后由操作员手动恢复') }}</label>
        <label><input v-model="form.proximityMode" type="radio" value="WARN_ONLY" /> {{ t('只报警：任务照常执行') }}</label>
      </fieldset>
      <label class="s-field"><span class="s-label">{{ t('水平基础距离') }}</span>
        <span class="s-input-row"><input v-model.number="form.proximityBaseM" class="input s-num num" type="number" min="3" max="100" /><span class="s-unit">m</span></span>
        <span class="s-hint">{{ t('两架都悬停时，水平距离小于它算靠近') }}</span></label>
      <label class="s-field"><span class="s-label">{{ t('反应时间') }}</span>
        <span class="s-input-row"><input v-model.number="form.proximityReactionS" class="input s-num num" type="number" min="0" max="10" step="0.5" /><span class="s-unit">s</span></span>
        <span class="s-hint">{{ t('接近速度 × 反应时间加到基础距离上') }}</span></label>
      <label class="s-field"><span class="s-label">{{ t('推算时长') }}</span>
        <span class="s-input-row"><input v-model.number="form.proximityLookaheadS" class="input s-num num" type="number" min="0" max="30" /><span class="s-unit">s</span></span></label>
      <label class="s-field"><span class="s-label">{{ t('高度差阈值') }}</span>
        <span class="s-input-row"><input v-model.number="form.proximityVerticalM" class="input s-num num" type="number" min="2" max="100" /><span class="s-unit">m</span></span>
        <span class="s-hint">{{ t('高度差不小于它时，水平再近也不算靠近') }}</span></label>
      <label class="s-field"><span class="s-label">{{ t('返航高度最小间隔') }}</span>
        <span class="s-input-row"><input v-model.number="form.rthSeparationM" class="input s-num num" type="number" min="0" max="200" /><span class="s-unit">m</span></span>
        <span class="s-hint">{{ t('起飞前检查：与另一架在空飞机的返航高度相差不足就拒绝（返航由飞机自己飞，平台插不上手）') }}</span></label>
    </div>
    <div class="row-end">
      <button class="btn btn-primary" :disabled="!changed() || saving" data-test="save-fleet-safety" @click="saveSafety">
        <AppIcon name="save" />{{ t('保存两机安全设置') }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.devices {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-sm);
}
.devices th {
  text-align: left;
  font-weight: 600;
  color: var(--text-dim);
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
}
.devices td {
  padding: 6px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.devices tr.off td {
  color: var(--text-dim);
}
.name {
  width: 7em;
}
.color {
  width: 36px;
  height: 26px;
  padding: 0;
  border: 1px solid var(--border);
  background: none;
}
.tag {
  margin-left: 6px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: var(--fs-xs);
  background: var(--surface-2, rgba(255, 255, 255, 0.08));
}
.mode {
  grid-column: 1 / -1;
  border: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.mode label {
  font-size: var(--fs-sm);
}
.row-end {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--sp-3, 12px);
}
</style>
