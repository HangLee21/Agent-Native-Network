
<script setup lang="ts">
/**
 * Manual (ui-design.md 5.10): safety first, how to read the live page, drone / S10 / Lite3 flows, terms, states and
 * errors, sources. Used full-page (top tab) and as the help panel over the main view (the "?" buttons), so reading
 * it mid-operation neither leaves the page nor hides the safety buttons.
 */
import { nextTick, onMounted, ref, watch } from 'vue'
import { lang, t } from '@/i18n'
import * as zh from './manualHtml'
import * as en from './manualHtml.en'

const props = defineProps<{ anchor?: string | null; panel?: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()
const body = ref<HTMLElement | null>(null)
// the English twin has the same structure and ids (switching language reloads the page)
const { MANUAL_BODY, MANUAL_TOC } = lang.value === 'en' ? en : zh

function go(id: string): void {
  const el = body.value?.querySelector<HTMLElement>(`#${CSS.escape(id)}`)
  if (!el) return
  el.scrollIntoView({ block: 'start' })
  if (el.tagName === 'TR') {
    el.classList.remove('hl')
    void el.offsetWidth
    el.classList.add('hl')
  }
}
onMounted(() => {
  if (props.anchor) void nextTick(() => go(props.anchor!))
})
watch(() => props.anchor, (a) => a && void nextTick(() => go(a)))
</script>

<template>
  <div class="manual" :class="{ panel }" data-test="manual">
    <nav class="mtoc" :aria-label="t('使用说明目录')">
      <button class="btn btn-sm back" data-test="manual-close" @click="emit('close')">{{ panel ? t('× 关闭说明（回到操作）') : t('← 回到实时监控') }}</button>
      <div class="mt">{{ t('使用说明') }}</div>
      <a v-for="item in MANUAL_TOC" :key="item.id" :class="{ sub: item.sub }" href="#" @click.prevent="go(item.id)">{{ item.label }}</a>
    </nav>
    <div ref="body" class="mbody scroll">
      <!-- static text written in this repository (generated from docs/dog/ui-prototype.html), no user content -->
      <article v-html="MANUAL_BODY" />
    </div>
  </div>
</template>

<style scoped>
.manual {
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
  background: var(--bg);
}
.manual.panel {
  border-right: 2px solid var(--accent);
  box-shadow: 8px 0 24px rgba(0, 0, 0, 0.35);
}
.mtoc { border-right: 1px solid var(--border); background: var(--panel); padding: 14px 12px; overflow: auto; }
.back { margin: 0 0 12px 6px; }
.mt { font-weight: 700; font-size: 15px; margin: 2px 8px 10px; }
.mtoc a { display: block; padding: 5px 10px; border-radius: 6px; color: var(--text-dim); text-decoration: none; font-size: 13.5px; cursor: pointer; }
.mtoc a:hover { background: var(--panel-2, var(--border)); color: var(--text); }
.mtoc a.sub { padding-left: 24px; font-size: 13px; }
.mbody { overflow: auto; padding: 22px 44px 80px; }
.mbody :deep(article) { max-width: 920px; }
.mbody :deep(h1) { font-size: 24px; margin: 0 0 4px; }
.mbody :deep(h2) { font-size: 19px; margin: 34px 0 10px; padding-top: 14px; border-top: 1px solid var(--border); }
.mbody :deep(h3) { font-size: 16px; margin: 22px 0 8px; }
.mbody :deep(h4) { font-size: 14.5px; margin: 18px 0 6px; }
.mbody :deep(.code) { display: inline-block; font-size: 11px; line-height: 16px; color: var(--text-dim); border: 1px solid var(--border); border-radius: 6px; padding: 0 5px; font-weight: 500; font-variant-numeric: tabular-nums; vertical-align: 1px; }
.mbody :deep(p), .mbody :deep(li) { line-height: 1.8; font-size: 14px; }
.mbody :deep(ol), .mbody :deep(ul) { padding-left: 22px; }
.mbody :deep(.lead) { color: var(--text-dim); }
.mbody :deep(.callout) { border: 1px solid var(--danger); background: color-mix(in srgb, var(--danger) 8%, transparent); border-radius: 10px; padding: 10px 16px; margin: 12px 0; }
.mbody :deep(.callout.info) { border-color: color-mix(in srgb, var(--accent) 50%, var(--border)); background: color-mix(in srgb, var(--accent) 7%, transparent); }
.mbody :deep(table.t) { border-collapse: collapse; width: 100%; font-size: 12.5px; }
.mbody :deep(table.t th) { text-align: left; color: var(--text-dim); font-weight: 600; font-size: 12px; padding: 5px 8px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); }
.mbody :deep(table.t td) { padding: 5px 8px; border-bottom: 1px solid color-mix(in srgb, var(--border) 60%, transparent); white-space: normal; vertical-align: top; line-height: 1.6; }
.mbody :deep(tr[id]), .mbody :deep(h2), .mbody :deep(h3) { scroll-margin-top: 44px; }
.mbody :deep(tr.hl td) { animation: hlfade 3s ease-out; }
.mbody :deep(.flowd) { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 8px 0 4px; }
.mbody :deep(.flowd b) { border: 1px solid var(--border); border-radius: 8px; padding: 3px 10px; background: var(--panel); font-weight: 600; font-size: 13px; }
.mbody :deep(.flowd i) { color: var(--text-dim); font-style: normal; }
.mbody :deep(.tbd) { display: inline-block; font-size: 10.5px; line-height: 16px; color: var(--warn); border: 1px solid color-mix(in srgb, var(--warn) 50%, transparent); border-radius: 8px; padding: 0 6px; font-weight: 500; white-space: nowrap; vertical-align: 1px; }
@keyframes hlfade {
  0%, 40% { background: color-mix(in srgb, var(--accent) 30%, transparent); }
  100% { background: transparent; }
}
</style>
