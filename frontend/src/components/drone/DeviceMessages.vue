<script setup lang="ts">
/**
 * Device messages and obstacle distances (D-18). Obstacle data comes from DRC hsi_info_push, so it
 * is only present while DRC is connected. HMS codes are shown raw (no official RC-scenario text table).
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useDeviceMessagesStore } from '@/stores/deviceMessages'
import { dateLocale, t } from '@/i18n'

const props = withDefaults(defineProps<{ limit?: number }>(), { limit: 8 })
const store = useDeviceMessagesStore()
const open = ref(true)
const shown = computed(() => store.list.slice(0, props.limit))
const fresh = computed(() => !!store.obstacles && Date.now() - store.obstacles.ts < 10_000)
const m = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)} m`)
const time = (ts: number) => new Date(ts).toLocaleTimeString(dateLocale(), { hour12: false })
</script>

<template>
  <div class="dm" data-test="device-messages">
    <div class="obstacles" :class="{ near: store.obstacles?.near }" data-test="obstacles">
      <AppIcon name="crosshair" :size="15" />
      <template v-if="store.obstacles">
        <span>{{ t('障碍物 水平') }} <b>{{ m(store.obstacles.horizontal) }}</b></span>
        <span>{{ t('上方') }} <b>{{ m(store.obstacles.up) }}</b></span>
        <span>{{ t('下方') }} <b>{{ m(store.obstacles.down) }}</b></span>
        <span v-if="!fresh" class="dim">{{ t('（数据已过时）') }}</span>
      </template>
      <span v-else class="dim">{{ t('障碍物距离：需 DRC 连接后才有数据') }}</span>
    </div>
    <button class="dm-toggle" :aria-expanded="open" @click="open = !open; store.unread = 0">
      <AppIcon :name="open ? 'down' : 'chevron'" :size="15" />{{ t('设备消息') }}
      <span v-if="store.unread && !open" class="badge">{{ store.unread }}</span>
    </button>
    <ul v-if="open" class="list">
      <li v-if="!shown.length" class="empty dim">{{ t('暂无设备消息') }}</li>
      <li v-for="msg in shown" :key="msg.id" :class="msg.level.toLowerCase()" :data-level="msg.level">
        <div class="row1"><b>{{ msg.title }}</b><span class="t">{{ time(msg.ts) }}</span></div>
        <div class="text">{{ msg.text }}</div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.dm {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.obstacles {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 6px var(--sp-2);
  border-radius: var(--r-ctl);
  background: var(--panel-2);
  font-size: var(--fs-xs);
}
.obstacles b {
  font-family: var(--font-num);
}
.obstacles.near {
  background: color-mix(in srgb, var(--warn) 18%, transparent);
  color: var(--warn);
}
.dm-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 0;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.badge {
  padding: 0 6px;
  border-radius: 8px;
  background: var(--accent);
  color: var(--bg, #000);
  font-size: var(--fs-xs);
}
.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.list li {
  padding: 4px var(--sp-2);
  border-left: 3px solid var(--border);
  background: var(--panel-2);
  border-radius: 0 var(--r-ctl) var(--r-ctl) 0;
  font-size: var(--fs-xs);
}
.list li.warning {
  border-left-color: var(--warn);
}
.list li.critical {
  border-left-color: var(--danger);
}
.list li.empty {
  border-left: none;
  background: none;
}
.row1 {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}
.t {
  color: var(--text-dim);
  font-family: var(--font-num);
}
.text {
  color: var(--text-dim);
  word-break: break-all;
}
.dim {
  color: var(--text-dim);
}
</style>
