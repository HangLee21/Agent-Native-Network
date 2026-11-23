<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { RouterView, useRoute, type RouteLocationNormalizedLoaded } from 'vue-router'
import StatusBar from '@/components/layout/StatusBar.vue'
import LinkChips from '@/components/layout/LinkChips.vue'
import ToastHost from '@/components/common/ToastHost.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import DogNavConfirm from '@/components/dog/DogNavConfirm.vue'
import AlertBanner from '@/components/layout/AlertBanner.vue'
import { useSystemStore } from '@/stores/system'
import { useSafetyStore } from '@/stores/safety'
import { useFleetStore } from '@/stores/fleet'

const system = useSystemStore()
const safety = useSafetyStore()
const fleet = useFleetStore()
let timer: number | undefined
const current = useRoute()
/** 监视台 opened in its own window (?window=1): audience screen, without the platform's top bar, alerts and notices. */
const bare = computed(() => current.name === 'watch' && current.query.window === '1')

/** Engineering pages follow the selected drone; /demo/* and pages marked meta.fleet === false do not. */
function droneBound(route: RouteLocationNormalizedLoaded): boolean {
  return route.meta.fleet !== false && !route.path.startsWith('/demo')
}

onMounted(() => {
  system.applyTheme(system.theme)
  void system.refresh()
  safety.start()
  // the fleet starts every known drone's stores (D-31)
  void fleet.start()
  timer = window.setInterval(() => void system.refresh(), 10000)
})

onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="shell">
    <StatusBar v-if="!bare">
      <template #status>
        <LinkChips />
      </template>
    </StatusBar>
    <AlertBanner v-if="!bare" />
    <main class="main">
      <RouterView v-slot="{ Component, route }">
        <!-- pages with their own data (demo pages, meta.fleet === false) neither wait for the fleet nor re-mount -->
        <component :is="Component" v-if="!droneBound(route)" />
        <!-- engineering pages re-mount when the selected drone changes: every panel and command is bound to one drone (D-31) -->
        <component :is="Component" v-else-if="fleet.ready" :key="fleet.selectedSn ?? 'none'" />
      </RouterView>
    </main>
    <ToastHost v-if="!bare" />
    <ConfirmDialog />
    <!-- dog navigation start / avoidance-off dialogs: render nothing until one is asked for (docs/dog/ui-design.md 19.3) -->
    <DogNavConfirm />
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.main {
  position: relative;
  flex: 1 1 0;
  min-height: 0;
}
</style>
