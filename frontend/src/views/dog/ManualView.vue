<script setup lang="ts">
/** The manual as its own page (top tab「使用说明」): for reading before operating. `?id=` jumps to an entry. */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ManualContent from '@/components/dog/ManualContent.vue'

const route = useRoute()
const router = useRouter()
const anchor = computed(() => (typeof route.query.id === 'string' ? route.query.id : null))
</script>

<template>
  <ManualContent :anchor="anchor" @close="router.push('/monitor')" />
</template>
