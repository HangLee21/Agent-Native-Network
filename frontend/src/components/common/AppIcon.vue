<script setup lang="ts">
/** Unified line icon set (ui-design.md §6: 1.75px stroke, 24px grid, inline SVG, no icon fonts). */
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

const paths: Record<string, string> = {
  map: 'M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Zm0 0v13m6-10.5v13',
  monitor: 'M3 6.5A1.5 1.5 0 0 1 4.5 5h11A1.5 1.5 0 0 1 17 6.5v11a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 3 17.5v-11ZM17 10l4-2.5v9L17 14',
  library: 'M4 5h16M4 10h16M4 15h10M4 20h7',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1a7.5 7.5 0 0 0 2 1.2l.4 2.6h5l.4-2.6a7.5 7.5 0 0 0 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3A4 4 0 0 0 11 18.7l1-1',
  shield: 'M12 3 5 6v5c0 4.5 3 8.5 7 10 4-1.5 7-5.5 7-10V6l-7-3Z',
  antenna: 'M12 12v9m-3 0h6M8.5 8.5a5 5 0 0 1 7 0M6 6a8.5 8.5 0 0 1 12 0M12 12a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z',
  battery: 'M3 8.5A1.5 1.5 0 0 1 4.5 7h13A1.5 1.5 0 0 1 19 8.5v7a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 3 15.5v-7ZM21 10.5v3',
  satellite: 'm7 13 4 4M4.5 10.5l3-3 9 9-3 3-9-9ZM14 7l3-3 3 3-3 3M13 20a7 7 0 0 0 7-7',
  alert: 'M12 4 2.5 20h19L12 4Zm0 6v4.5m0 2.5v.5',
  plus: 'M12 5v14M5 12h14',
  trash: 'M4 7h16M9 7V4.5h6V7m-8 0 1 13h8l1-13',
  up: 'm6 15 6-6 6 6',
  down: 'm6 9 6 6 6-6',
  save: 'M5 4h11l3 3v13H5V4Zm3 0v5h7V4M8 20v-6h8v6',
  sync: 'M4 12a8 8 0 0 1 13.7-5.7L20 8.5M20 4v4.5h-4.5M20 12a8 8 0 0 1-13.7 5.7L4 15.5M4 20v-4.5h4.5',
  play: 'M7 5v14l12-7L7 5Z',
  stop: 'M6 6h12v12H6z',
  home: 'm3 11 9-7 9 7m-15-1.5V20h4.5v-5.5h3V20H18v-10.5',
  takeoff: 'M12 20V6m-6 6 6-6 6 6M5 3h14',
  estop: 'M8.3 3h7.4L21 8.3v7.4L15.7 21H8.3L3 15.7V8.3L8.3 3ZM8 12h8',
  check: 'm5 12.5 4.5 4.5L19 7.5',
  x: 'M6 6l12 12M18 6 6 18',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-13v4.5l3 2',
  spinner: 'M12 3a9 9 0 1 0 9 9',
  layers: 'm12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5',
  swap: 'M7 4 3 8l4 4M3 8h14M17 20l4-4-4-4m4 4H7',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4V8Zm8 9a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z',
  record: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z',
  crosshair: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM12 3v4m0 10v4M3 12h4m10 0h4',
  chevron: 'm9 6 6 6-6 6',
  left: 'm15 6-6 6 6 6',
  lock: 'M6 11h12v9H6v-9Zm2.5 0V8a3.5 3.5 0 0 1 7 0v3',
  'lock-open': 'M6 11h12v9H6v-9Zm2.5 0V8a3.5 3.5 0 0 1 6.8-1.2',
  joystick: 'M12 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 0v6M5 15h14l1.5 5h-17L5 15Z',
  bell: 'M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Zm4 4a2 2 0 0 0 4 0',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Zm9.5 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  sun: 'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0-13v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z',
  upload: 'M12 16V4m-5 5 5-5 5 5M4 20h16',
  download: 'M12 4v12m-5-5 5 5 5-5M4 20h16',
  copy: 'M9 9h11v11H9zM15 9V4H4v11h5',
  edit: 'm4 20 1-4L16 5l3 3L8 19l-4 1Zm10-13 3 3',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-10v6m0-9v.5',
  target: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm0-5a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0-3.5a.5.5 0 1 0 0-1 .5.5 0 0 0 0 1Z',
  drone: 'M9 9h6v6H9zM9 9 5.5 5.5M15 9l3.5-3.5M9 15l-3.5 3.5M15 15l3.5 3.5M5.5 5.5m-2.5 0a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0M18.5 5.5m-2.5 0a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0M5.5 18.5m-2.5 0a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0M18.5 18.5m-2.5 0a2.5 2.5 0 1 0 5 0 2.5 2.5 0 1 0-5 0',
  land: 'M12 4v14m-6-6 6 6 6-6M5 21h14',
  orbit: 'M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM12 4a8 8 0 1 1-7.4 5M3 4.5l1.6 4.5 4.4-1.6',
  gimbal: 'M12 3v4M7 7h10v5a5 5 0 0 1-10 0V7Zm5 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  zoom: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Zm4.6-1.9L20 20M8 10.5h5m-2.5-2.5v5',
  file: 'M6 3h8l4 4v14H6V3Zm8 0v4h4',
  ai: 'M11 3l1.8 4.6 4.7 1.9-4.7 1.8L11 16l-1.8-4.7-4.7-1.8 4.7-1.9L11 3Zm7 11 .9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9.9-2.1Z',
  pin: 'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11Zm0-9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z',
  route: 'm4 19 5-8 5 5 6-10M4 19h.01M20 6h.01',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  'panel-close': 'm6 6 6 6-6 6m7-12 6 6-6 6',
  'panel-open': 'm18 6-6 6 6 6m-7-12-6 6 6 6',
  sliders: 'M4 7h9m4 0h3M4 17h3m4 0h9M15 5v4M9 15v4',
  minus: 'M5 12h14',
  'eye-off': 'M3 3l18 18M10.6 5.6c.5-.1.9-.1 1.4-.1 6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-2.4 3.2M6.5 6.5C4 8.2 2.5 12 2.5 12S6 18.5 12 18.5c1.6 0 3-.4 4.3-1.1M9.9 9.9a3 3 0 0 0 4.2 4.2',
}

const d = computed(() => paths[props.name] ?? paths.info)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="app-icon"
    :class="{ spin: name === 'spinner' }"
  >
    <path :d="d" />
  </svg>
</template>

<style scoped>
.app-icon {
  flex: none;
}
.spin {
  animation: spin 0.9s linear infinite;
}
</style>
