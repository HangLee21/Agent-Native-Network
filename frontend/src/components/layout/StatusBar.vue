<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import { useSystemStore } from '@/stores/system'
import markReverse from '@/assets/brand/embonet-mark-reverse.svg'
import markColor from '@/assets/brand/embonet-mark-color.svg'
import { useDogStore } from '@/stores/dog'
import { dog2Api } from '@/api/dogv2'
import { t, tc } from '@/i18n'

const system = useSystemStore()

const router = useRouter()
const BASE_TABS = [
  { to: '/plan', label: t('规划'), icon: 'map' },
  { to: '/monitor', label: t('实时监控'), icon: 'monitor' },
  { to: '/network', label: t('网络观测'), icon: 'layers' },
  { to: '/watch', label: t('监视台'), icon: 'eye' },
  { to: '/history', label: tc('tab', '记录'), icon: 'clock' },
  { to: '/settings', label: t('设置'), icon: 'settings' },
]
/** The demo console (R-33) is its own page; shown once its route is registered. */
const DEMO_TAB = { to: '/demo/console', label: tc('tab', '演示控制'), icon: 'play' }
/** Manual for drones and robot dogs (docs/dog/ui-design.md 5.10), last tab. */
const MANUAL_TAB = { to: '/manual', label: t('使用说明'), icon: 'file' }
/** The new dog system's test page (docs/dog/v2/design.md 4): only when DOG2_MODE is not off, so nothing changes otherwise. */
const DOG2_TAB = { to: '/dog2', label: t('新狗系统'), icon: 'layers' }
const dog2On = ref(false)
onMounted(() => {
  dog2Api.list().then((r) => { dog2On.value = r.mode !== 'off' }).catch(() => undefined)
})
const tabs = computed(() => [...(router.resolve(DEMO_TAB.to).matched.length ? [...BASE_TABS, DEMO_TAB] : BASE_TABS),
  ...(dog2On.value ? [DOG2_TAB] : []), MANUAL_TAB])

const isMock = computed(() => system.info?.gatewayMode === 'mock')
/** EmboNet brand (src/assets/brand/README.md): reverse on the dark top bar, colour on the white outdoor one. */
const outdoor = computed(() => system.theme === 'outdoor')
/** With robot dogs the status area has two more chips: the tabs get narrower padding so everything stays on one line. */
const dogs = useDogStore()

function toggleTheme(): void {
  system.applyTheme(system.theme === 'dark' ? 'outdoor' : 'dark')
}
</script>

<template>
  <header class="topbar" :class="{ crowded: dogs.present }">
    <div class="brand" :class="{ outdoor }" role="img" aria-label="EmboNet">
      <img class="mark" :src="outdoor ? markColor : markReverse" alt="" width="31" height="34" />
      <span class="word"><span class="embo">Embo</span><span class="net">Net</span></span>
    </div>
    <nav class="tabs" :aria-label="t('页面')">
      <RouterLink v-for="t in tabs" :key="t.to" :to="t.to" class="tab" active-class="active">
        <AppIcon :name="t.icon" :size="17" />
        <span>{{ t.label }}</span>
      </RouterLink>
    </nav>
    <div class="status">
      <span v-if="system.backendReachable === false" class="chip danger" data-test="backend-down">
        <span class="dot" />{{ t('后端未连接') }}
      </span>
      <slot name="status" />
      <span v-if="isMock" class="chip warn mock" :title="t('当前为模拟设备，所有飞行均为仿真')">{{ tc('tab', '模拟模式') }}</span>
      <button class="btn btn-ghost btn-icon" :title="system.theme === 'dark' ? t('切换为户外高亮主题') : t('切换为夜间主题')" @click="toggleTheme">
        <AppIcon :name="system.theme === 'dark' ? 'sun' : 'moon'" />
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  flex: none; /* never shrink when page content is tall */
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  padding: 0 var(--sp-4);
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  position: relative;
  z-index: 1000;
}
/* Poppins 400, Latin subset, bundled (OFL, src/assets/fonts): the field server cannot rely on Google Fonts */
@font-face {
  font-family: 'EmboNet Poppins';
  font-style: normal;
  font-weight: 400;
  font-display: block;
  src: url('@/assets/fonts/poppins-latin-400-normal.woff2') format('woff2');
}
/* lockup ≈ 128 × 34 px (min 120 × 24; mark alone min 16), wordmark in the logo sheet's proportions; clear space ≥ ¼ mark height */
.brand {
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  flex: none;
}
.brand .mark {
  display: block;
  width: auto;
  height: 34px;
}
.brand .word {
  font-family: 'EmboNet Poppins', sans-serif;
  font-weight: 400;
  font-size: 20px;
  letter-spacing: -0.005em;
  line-height: 1;
}
/* reverse on the dark top bar: white + Teal Light; colour on the white outdoor top bar: Graphite + Embo Teal */
.brand .embo {
  color: #ffffff;
}
.brand .net {
  color: #3fc1c0;
}
.brand.outdoor .embo {
  color: #23292f;
}
.brand.outdoor .net {
  color: #16888a;
}
.tabs {
  display: flex;
  gap: var(--sp-1);
  height: 100%;
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 var(--sp-3);
  white-space: nowrap; /* a label never breaks into two lines */
  color: var(--text-dim);
  text-decoration: none;
  font-weight: 600;
  border-bottom: 2px solid transparent;
}
.tab:hover {
  color: var(--text);
}
.tab.active {
  color: var(--text);
  border-bottom-color: var(--accent);
}
@media (max-width: 1700px) {
  .topbar.crowded .tab {
    padding: 0 var(--sp-2);
  }
  .topbar.crowded .status {
    gap: 6px;
  }
}
/* with dogs up to 1600 px wide: tab labels without icons (as below 1100 px without dogs), so the dog chips, whose text
   grows ("导航中", "别处控制"), never squeeze the theme button */
@media (max-width: 1600px) {
  .topbar.crowded .tab :deep(.app-icon) {
    display: none;
  }
}
.status {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  overflow: hidden;
}
.mock {
  color: var(--warn);
  font-weight: 700;
}
@media (max-width: 1280px) {
  .brand span {
    display: none;
  }
}
/* narrow windows: labels without icons, so the tabs and the status chips still fit on one line */
@media (max-width: 1100px) {
  .tab {
    padding: 0 var(--sp-2);
  }
  .tab :deep(.app-icon) {
    display: none;
  }
}
</style>
