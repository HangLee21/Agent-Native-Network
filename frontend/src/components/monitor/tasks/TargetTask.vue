<script setup lang="ts">
/** Target selection (R-24 ~ R-27 draft): the existing target panel and card inside a task card. */
import { computed } from 'vue'
import TaskCardShell from '../TaskCardShell.vue'
import TargetPanel from '@/components/target/TargetPanel.vue'
import { useTargetsStore } from '@/stores/targets'
import { STATE_LABELS } from '@/api/targets'
import { t } from '@/i18n'

const targets = useTargetsStore()
const state = computed(() => (targets.selecting ? t('视频选择中') : targets.selected ? STATE_LABELS[targets.selected.state] : ''))
</script>

<template>
  <TaskCardShell task="tgt" :title="t('目标')" icon="crosshair" :state="state">
    <TargetPanel :show-ai="false" />
  </TaskCardShell>
</template>
