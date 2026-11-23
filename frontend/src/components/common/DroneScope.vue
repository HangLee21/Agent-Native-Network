<script setup lang="ts">
/** Binds its content to one drone (D-31): stores and commands used inside go to that drone. */
import { provideDrone } from '@/composables/useDrone'

const props = defineProps<{ sn: string }>()
provideDrone(props.sn)
</script>

<template>
  <slot />
</template>
