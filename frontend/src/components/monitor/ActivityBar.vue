<script setup lang="ts">
/**
 * Latest commands above the safety area (S-03, D-18): the selected drone's last two commands with their device
 * receipts (one on small screens); it opens the full receipt log and the device messages / obstacle distances.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import CommandLog from '@/components/control/CommandLog.vue'
import DeviceMessages from '@/components/drone/DeviceMessages.vue'
import { useControlStore } from '@/stores/control'
import { useDeviceMessagesStore } from '@/stores/deviceMessages'
import { useFleetStore } from '@/stores/fleet'
import { time } from '@/utils/format'
import { t } from '@/i18n'

const control = useControlStore()
const messages = useDeviceMessagesStore()
const fleet = useFleetStore()
const open = ref(false)
const tab = ref<'cmd' | 'msg'>('cmd')
const recent = computed(() => control.commands.slice(0, 2))
const who = computed(() => (fleet.drones.length > 1 ? ` · ${fleet.label(control.sn)}` : ''))

function toggle(): void {
  open.value = !open.value
  if (open.value && tab.value === 'msg') messages.unread = 0
}
function show(which: 'cmd' | 'msg'): void {
  tab.value = which
  if (which === 'msg') messages.unread = 0
}
</script>

<template>
  <div class="activity" data-test="activity-bar">
    <button class="bar" :aria-expanded="open" @click="toggle">
      <span class="label">{{ t('最近指令') }}{{ who }}</span>
      <span v-if="messages.unread" class="badge">{{ t('消息 {n}', { n: messages.unread }) }}</span>
      <span class="go">{{ t('全部') }}<span class="long">{{ t('回执与设备消息') }}</span><AppIcon :name="open ? 'down' : 'up'" :size="13" /></span>
    </button>
    <ul class="recent" data-test="recent-commands">
      <li v-if="!recent.length" class="empty">{{ t('暂无指令') }}</li>
      <li v-for="c in recent" :key="c.id">
        <span class="t num">{{ time(c.createdAt) }}</span><span class="lb">{{ c.label }}</span><CommandStatus class="st" :record="c" compact />
      </li>
    </ul>
    <div v-if="open" class="pop">
      <div class="tabs" role="tablist" :aria-label="t('动态')">
        <button role="tab" :aria-selected="tab === 'cmd'" :class="{ on: tab === 'cmd' }" @click="show('cmd')">{{ t('指令回执') }}</button>
        <button role="tab" :aria-selected="tab === 'msg'" :class="{ on: tab === 'msg' }" @click="show('msg')">{{ t('设备消息与避障') }}<span v-if="messages.unread" class="badge">{{ messages.unread }}</span></button>
      </div>
      <div class="body scroll">
        <CommandLog v-if="tab === 'cmd'" :limit="8" />
        <DeviceMessages v-else />
      </div>
    </div>
  </div>
</template>

<style scoped>
.activity {
  position: relative;
  flex: none;
  padding: 4px var(--sp-3) 2px;
  border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel-2) 45%, var(--panel));
}
.bar {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 2px 0;
  background: transparent;
  border: 0;
  color: var(--text-dim);
  font: inherit;
  font-size: var(--fs-xs);
  text-align: left;
  cursor: pointer;
}
.label {
  white-space: nowrap;
}
.go {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--accent);
}
.recent {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.recent li {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) auto;
  gap: 6px;
  align-items: center;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: var(--fs-xs);
}
.recent li:nth-child(odd) {
  background: var(--panel-2);
}
.recent .t {
  color: var(--text-dim);
}
.recent .lb {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent .st {
  max-width: 170px;
}
.recent .empty {
  display: block;
  color: var(--text-dim);
}
/* small screens: one line — the latest command, then the link to all receipts */
@media (max-height: 800px) {
  .activity {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    padding: 3px var(--sp-3);
  }
  .recent {
    order: 1;
    flex: 1;
    min-width: 0;
  }
  .recent li + li {
    display: none;
  }
  .bar {
    order: 2;
    width: auto;
    flex: none;
  }
  .bar .label,
  .bar .long,
  .recent .t {
    display: none;
  }
  .recent li {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
.badge {
  flex: none;
  padding: 0 6px;
  border-radius: 8px;
  background: var(--warn);
  color: #1a1205;
  font-size: 11px;
  font-weight: 700;
}
.pop {
  position: absolute;
  left: var(--sp-2);
  right: var(--sp-2);
  bottom: calc(100% + 6px);
  z-index: 40;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}
.tabs button {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 36px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-dim);
  font: inherit;
  font-size: var(--fs-sm);
  font-weight: 600;
  cursor: pointer;
}
.tabs button.on {
  color: var(--text);
  border-bottom-color: var(--accent);
}
.body {
  padding: var(--sp-2);
  overflow-y: auto;
}
</style>
