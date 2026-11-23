<script setup lang="ts">
/** Layer management (R-04): every information type is a toggleable layer with a legend colour. */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { LAYERS, useLayersStore } from '@/stores/layers'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ defaultOpen?: boolean }>(), { defaultOpen: true })
const layers = useLayersStore()
const open = ref(props.defaultOpen)
const groups = computed(() => {
  const out: Record<string, typeof LAYERS> = {}
  for (const l of LAYERS) (out[l.group] ??= []).push(l)
  return out
})
</script>

<template>
  <div class="layer-panel" :class="{ collapsed: !open }" data-test="layer-panel">
    <button class="head" :aria-expanded="open" :title="t('图层')" @click="open = !open">
      <AppIcon name="layers" />
      <span v-if="open">{{ t('图层') }}</span>
      <AppIcon v-if="open" name="x" :size="16" class="close" />
    </button>
    <div v-if="open" class="body">
      <section v-if="layers.baseMaps.length > 1" data-test="base-maps">
        <h4 class="section-title">{{ t('底图') }}</h4>
        <label v-for="b in layers.baseMaps" :key="b.id" class="item">
          <input
            type="radio"
            name="base-map"
            :checked="layers.baseMapId === b.id"
            :data-base-map="b.id"
            @change="layers.setBaseMap(b.id)"
          />
          <span class="label">{{ b.label }}</span>
          <span class="tag">{{ b.coordSys === 'GCJ02' ? 'GCJ-02' : 'WGS84' }}</span>
        </label>
      </section>
      <section v-for="(items, g) in groups" :key="g">
        <h4 class="section-title">{{ g }}</h4>
        <label v-for="l in items" :key="l.id" class="item" :class="{ disabled: l.unavailable }" :title="l.unavailable ?? ''">
          <input
            type="checkbox"
            :checked="layers.isVisible(l.id)"
            :disabled="!!l.unavailable"
            :data-layer="l.id"
            @change="layers.set(l.id, ($event.target as HTMLInputElement).checked)"
          />
          <span class="swatch" :style="{ background: l.color }" />
          <span class="label">{{ l.label }}</span>
          <span v-if="l.unavailable" class="tag">{{ t('不可用') }}</span>
        </label>
        <p v-for="l in items.filter((x) => x.unavailable)" :key="l.id + '-why'" class="why">{{ l.unavailable }}</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.layer-panel {
  width: 260px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--r-panel);
  box-shadow: var(--shadow);
  font-size: var(--fs-sm);
}
.layer-panel.collapsed {
  width: auto;
}
.head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  width: 100%;
  min-height: 40px;
  padding: 0 var(--sp-3);
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.head .close {
  margin-left: auto;
  color: var(--text-dim);
}
.body {
  padding: 0 var(--sp-3) var(--sp-3);
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  max-height: 60vh;
  overflow: auto;
}
.item {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  min-height: 30px;
  cursor: pointer;
}
.item input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}
.item.disabled {
  cursor: not-allowed;
  color: var(--text-dim);
}
.swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex: none;
}
.label {
  flex: 1;
}
.why {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
