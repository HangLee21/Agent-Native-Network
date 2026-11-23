<script setup lang="ts">
/** A dog's camera as a small-window tile (ui-design.md 5.2): S10 a frame every ~2 s to spare the tunnel, with its age;
 *  Lite3 the new dog system's live colour video (since 2026-11-10). */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useDogStore, DOG_NAME } from '@/stores/dog'
import { s10MediaUrl, type DogId } from '@/api/dog'
import Dog2Video from '@/components/dogv2/Dog2Video.vue'
import { useDog2Store } from '@/stores/dogv2'
import { t } from '@/i18n'

const props = defineProps<{ dog: DogId }>()
const store = useDogStore()
const stamp = ref(Date.now())
let timer = 0
onMounted(() => (timer = window.setInterval(() => (stamp.value = Date.now()), 2000)))
onBeforeUnmount(() => window.clearInterval(timer))

const src = computed(() => {
  void stamp.value
  if (props.dog === 's10') {
    const r = store.s10?.topics.rgb
    return r?.image ? s10MediaUrl(r.image, Math.floor(stamp.value / 2000)) : null
  }
  return null
})
const v2 = useDog2Store()
const l3d = computed(() => (props.dog === 'lite3' ? v2.dogs.find((d) => d.model === 'lite3') ?? null : null))
const age = computed(() =>
  props.dog === 's10'
    ? store.age('s10.rgb', store.s10?.topics.rgb?.age, store.s10?.stateAt)
    : l3d.value?.video?.rgb?.state === 'live' ? 0 : null,
)
const failed = ref(false)
// a frame that failed once (dog busy, tunnel hiccup) must not hide the tile for good: try again with the next one
watch(src, () => (failed.value = false))
</script>

<template>
  <div class="thumb" :class="{ offl: !store.online(dog) }" data-test="dog-thumb">
    <Dog2Video v-if="l3d" class="l3thumb" :dog="l3d.id" stream="rgb" :video="l3d.video?.rgb" />
    <img v-else-if="src && !failed" :src="src" :alt="t('{name} 相机缩略图', { name: DOG_NAME[dog] })" @error="failed = true" @load="failed = false" />
    <div v-else class="empty">{{ store.online(dog) ? t('没有新画面') : store.pageStale(dog) ? t('没更新') : t('离线') }}</div>
  </div>
  <span class="tile-tag chip"><span class="dot" :style="{ background: `var(--dog-${dog})` }" />{{ t('{name} 相机 · {age}（缩略）', { name: DOG_NAME[dog], age: age == null ? '—' : t('{n} 秒前', { n: age.toFixed(1) }) }) }}</span>
</template>

<style scoped>
.thumb { position: absolute; inset: 0; background: #000; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.l3thumb { position: absolute; inset: 0; border-radius: 0; aspect-ratio: auto; }
.offl img { filter: grayscale(1) brightness(0.6); }
.empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-dim); font-size: var(--fs-xs); }
.tile-tag { position: absolute; left: 6px; top: 6px; z-index: 2; height: 24px; padding: 0 8px; background: var(--overlay); font-size: var(--fs-xs); }
</style>
