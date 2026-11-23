<script setup lang="ts">
/** Four-legged robot icon for dog chips and cards (same stroke style as AppIcon). */
withDefaults(defineProps<{ size?: number }>(), { size: 16 })
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"
       stroke-linejoin="round" aria-hidden="true">
    <path d="M4 10h11l2-3h3v3l-2 2v1H5zM6 13v5M9 13v5M14 13v5M17 13v5M18 7l1-2" />
  </svg>
</template>
