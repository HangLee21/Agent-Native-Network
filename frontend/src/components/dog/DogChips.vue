<script setup lang="ts">
/** Top-bar chips of the dogs, next to the drone chips: click = operate this dog (ui-design.md 5.1). */
import { computed } from 'vue'
import DogIcon from './DogIcon.vue'
import { useDogStore, navActive, S10_POSTURE, DOG_NAME } from '@/stores/dog'
import { lite3Battery, s10RunningJob } from './dogFlow'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'

const emit = defineEmits<{ (e: 'select', id: DogId): void }>()
const store = useDogStore()

function text(id: DogId): string {
  if (store.lost(id)) return t('失联')
  if (store.pageStale(id)) return t('没更新')
  if (!store.online(id)) return t('离线')
  if (id === 's10') {
    const s = store.s10!
    if (store.s10Hold) return t('移动中')
    if (navActive(s.nav)) return t('导航中')
    if (s10RunningJob(s)) return t('执行中')
    return S10_POSTURE[s.posture ?? ''] ?? t('在线')
  }
  const l = store.lite3!
  if (l.robot.controller === 'other') return t('别处控制')
  const b = lite3Battery(l)
  return b == null ? t('在线') : `${b}%`
}
const moving = (id: DogId) => store.online(id) && (id === 's10' ? !!store.s10Hold || !!s10RunningJob(store.s10) || navActive(store.s10?.nav) : store.l3Moving)
const list = computed(() => store.ids)
</script>

<template>
  <button v-for="id in list" :key="id" class="chip dog" :class="[{ on: store.selected === id }, store.lost(id) ? 'danger' : !store.online(id) ? 'off' : '']"
          :style="{ '--c': `var(--dog-${id})` }" :title="t('{name}：{state}（点击切换到它）', { name: DOG_NAME[id], state: text(id) })" data-test="dog-chip" @click="emit('select', id)">
    <span class="ic" :class="{ move: moving(id) }"><DogIcon :size="15" /></span><b>{{ DOG_NAME[id] }}</b><span class="num">{{ text(id) }}</span>
  </button>
</template>

<style scoped>
.dog { gap: 5px; cursor: pointer; font: inherit; }
.dog .ic { display: inline-flex; color: var(--c); }
.dog .ic.move { animation: pulse 1s infinite; }
.dog.on { outline: 2px solid var(--c); outline-offset: -1px; }
.dog.off { opacity: 0.6; }
@keyframes pulse { 50% { opacity: 0.3; } }
</style>
