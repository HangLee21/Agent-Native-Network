<script setup lang="ts">
/**
 * Inside the editor: which other saved routes are drawn on the map with the edited one (dual-drone planning,
 * 2026-11-04). Same choice as the eyes in the route list.
 */
import { computed, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useRoutesStore } from '@/stores/routes'
import { useRouteOverlaysStore } from '@/stores/routeOverlays'
import { useEditorStore } from '@/stores/editor'
import { t } from '@/i18n'

const routes = useRoutesStore()
const ov = useRouteOverlaysStore()
const ed = useEditorStore()
const open = ref(false)

const others = computed(() => routes.list.filter((r) => r.id !== ed.draft?.id))
const shownNames = computed(() => others.value.filter((r) => ov.isShown(r.id)).map((r) => r.name))

onMounted(() => {
  if (!routes.loaded) void routes.refresh()
})
watch(() => routes.list, (l) => ov.sync(l))
</script>

<template>
  <div class="picker" data-test="overlay-picker">
    <button class="toggle" :aria-expanded="open" @click="open = !open">
      <span class="t"><AppIcon :name="open ? 'down' : 'chevron'" :size="16" />{{ t('地图上一起显示') }}</span>
      <span class="dim">{{ shownNames.length ? shownNames.join(t('、')) : t('无（展开后勾选其他航线）') }}</span>
    </button>
    <div v-if="open" class="items">
      <p v-if="!others.length" class="dim empty">{{ t('还没有其他已保存的航线') }}</p>
      <label v-for="r in others" :key="r.id" class="item">
        <input type="checkbox" :checked="ov.isShown(r.id)" data-test="overlay-check" @change="ov.toggle(r.id)" />
        <i class="swatch" :style="{ background: ov.colorOf(r.id) ?? 'transparent' }" />
        <span class="grow">{{ r.name }}</span>
        <span class="dim num">{{ t('{n} 点 · 最高 {h} m', { n: r.waypointCount, h: r.maxHeight }) }}</span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.picker {
  margin: 0 var(--sp-4);
  border-top: 1px solid var(--border);
}
.toggle {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 2px;
  width: 100%;
  padding: 6px 0;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
}
.toggle .t {
  display: flex;
  align-items: center;
  gap: 6px;
}
.toggle .dim {
  padding-left: 22px;
  font-weight: 400;
  font-size: var(--fs-xs);
}
.items {
  display: flex;
  flex-direction: column;
  padding-bottom: var(--sp-2);
  max-height: 180px;
  overflow: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 2px;
  font-size: var(--fs-sm);
  cursor: pointer;
}
.item input {
  accent-color: var(--accent);
}
.item .grow {
  overflow-wrap: anywhere;
}
.item .dim {
  flex: none;
  font-size: var(--fs-xs);
}
.swatch {
  width: 14px;
  height: 3px;
  flex: none;
}
.empty {
  margin: 0;
  font-size: var(--fs-sm);
}
</style>
