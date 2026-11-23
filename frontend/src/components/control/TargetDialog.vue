<script setup lang="ts">
/** Confirms a map-picked flyto target, POI centre (R-13) or a map target for target selection (R-24 draft). */
import { ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = defineProps<{ kind: 'flyto' | 'poi' | 'target'; point: LatLon; defaultHeight: number }>()
const emit = defineEmits<{ (e: 'confirm', height: number, speed: number): void; (e: 'cancel'): void }>()
const height = ref(Math.round(props.defaultHeight))
const speed = ref(8)
</script>

<template>
  <div class="backdrop">
    <form class="dialog panel" role="dialog" aria-modal="true" @submit.prevent="emit('confirm', height, speed)">
      <div class="panel-head"><span class="row"><AppIcon :name="kind === 'poi' ? 'orbit' : kind === 'target' ? 'crosshair' : 'target'" />{{ kind === 'flyto' ? t('飞向目标点') : kind === 'target' ? t('设为目标') : t('兴趣点环绕') }}</span></div>
      <div class="panel-body">
        <p class="num dim">{{ point.lat.toFixed(7) }}, {{ point.lon.toFixed(7) }}{{ t('（WGS84）') }}</p>
        <div class="grid">
          <label class="field"><span>{{ kind === 'poi' ? t('中心高度（m，相对起飞点）') : kind === 'target' ? t('目标高度（地面约为 0）（m，相对起飞点）') : t('目标高度（m，相对起飞点）') }}</span><input v-model.number="height" class="input num" type="number" /></label>
          <label v-if="kind === 'flyto'" class="field"><span>{{ t('最大速度（m/s）') }}</span><input v-model.number="speed" class="input num" type="number" min="1" max="15" /></label>
        </div>
        <p class="note">{{ kind === 'flyto' ? t('飞机到点后悬停。低于 20 m 时会先爬升到 20 m（大疆限制）。目标点须通过安全层校验。') : kind === 'target' ? t('只创建目标并让相机看向它，飞机不会移动；之后在目标卡片中选择动作。') : t('飞机以当前位置到中心的距离为半径环绕，可在环绕卡片中调整速度，用底部「退出环绕」退出。') }}</p>
      </div>
      <div class="actions">
        <button type="button" class="btn" @click="emit('cancel')">{{ t('取消') }}</button>
        <button type="submit" class="btn btn-primary" data-test="target-confirm">{{ kind === 'flyto' ? t('飞往此处') : kind === 'target' ? t('设为目标') : t('开始环绕') }}</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  z-index: 2400;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog {
  width: 440px;
  box-shadow: var(--shadow);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--sp-3);
}
.grid .input {
  width: 100%;
}
.note {
  font-size: var(--fs-xs);
  color: var(--text-dim);
  margin: var(--sp-3) 0 0;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-2);
  padding: 0 var(--sp-4) var(--sp-4);
}
</style>
