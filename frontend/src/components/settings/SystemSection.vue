<script setup lang="ts">
/**
 * 系统与接入 section of the settings page: the interface language (docs/i18n.md), system info and the external
 * interfaces (R-16, R-17, R-26 draft). Only the language can be changed here; it is kept in this browser.
 */
import { useSystemStore } from '@/stores/system'
import { useLayersStore } from '@/stores/layers'
import { config as runtimeConfig } from '@/config/runtime'
import { lang, setLang, t, type Lang } from '@/i18n'

const system = useSystemStore()
const layers = useLayersStore()
const cfg = runtimeConfig()
/** Each language is named in itself, so it can be found whichever language is showing. */
const LANGS: { value: Lang; label: string }[] = [
  { value: 'zh', label: '中文' }, // i18n-ignore
  { value: 'en', label: 'English' },
]
</script>

<template>
  <section class="panel s-card" aria-labelledby="settings-lang-title" data-test="settings-language">
    <div class="s-card-head"><h2 id="settings-lang-title">{{ t('界面语言') }}<span v-if="lang === 'zh'" class="alt"> · Language</span></h2></div>
    <div class="seg" role="radiogroup" aria-labelledby="settings-lang-title">
      <label v-for="o in LANGS" :key="o.value" class="seg-opt" :lang="o.value === 'zh' ? 'zh-CN' : 'en'">
        <input type="radio" name="settings-lang" :value="o.value" :checked="lang === o.value" :data-test="`lang-${o.value}`"
          @change="setLang(o.value)" />
        {{ o.label }}
      </label>
    </div>
    <p class="s-note">{{ t('默认中文。只对这台电脑上的这个浏览器生效，切换后页面会重新加载。') }}</p>
  </section>

  <section class="panel s-card" aria-labelledby="settings-system-title">
    <div class="s-card-head"><h2 id="settings-system-title">{{ t('系统信息') }}</h2></div>
    <dl class="s-dl">
      <dt>{{ t('网关模式') }}</dt><dd>{{ system.info?.gatewayMode === 'mock' ? t('模拟（mock）') : system.info?.gatewayMode ?? '—' }}</dd>
      <dt>{{ t('遥控器 SN') }}</dt><dd class="num">{{ system.info?.gateway?.gatewaySn ?? t('多台（见「设备与两机安全」）') }}</dd>
      <dt>{{ t('飞行器') }}</dt><dd class="num">{{ system.info?.gateway?.droneModel ?? '—' }} · {{ system.info?.gateway?.droneSn ?? '—' }}</dd>
      <dt>{{ t('航线执行方式') }}</dt><dd>{{ system.info?.routeExecutionMode === 'CONTINUOUS_UPDATE' ? t('途中更新') : t('逐点飞行（到点后再飞下一点）') }}</dd>
      <dt>{{ t('后端地址') }}</dt><dd class="num">{{ cfg.apiBaseUrl }}</dd>
      <dt>{{ t('底图坐标系') }}</dt><dd>{{ t('{sys}（{label}）', { sys: layers.baseMap.coordSys, label: layers.baseMap.label }) }}</dd>
    </dl>
  </section>

  <section class="panel s-card api" aria-labelledby="settings-api-title">
    <div class="s-card-head"><h2 id="settings-api-title">{{ t('外部接口（给其他软件和 AI 用）') }}</h2></div>
    <h3 class="s-sub">{{ t('外部航点接口（R-16 / R-17）') }}</h3>
    <code class="s-code">POST {{ cfg.apiBaseUrl }}/api/v1/external/routes</code>
    <code class="s-code">POST {{ cfg.apiBaseUrl }}/api/v1/external/routes/import{{ t('（KMZ / GeoJSON / CSV）') }}</code>
    <p class="s-note">{{ t('提交的航线与手绘航线使用同一模型，并经过同一安全层校验。若配置了 EXTERNAL_API_KEY，请在请求头 X-API-Key 中携带。') }}</p>
    <h3 class="s-sub">{{ t('AI 目标建议接口（R-26 草案）') }}</h3>
    <code class="s-code">POST {{ cfg.apiBaseUrl }}/api/v1/external/targets{{ t('（请求头 X-AI-Key）') }}</code>
    <code class="s-code">{"source":"detector","label":"vehicle","confidence":0.9,"suggestedAction":"APPROACH","image":{"lens":"wide","box":[0.4,0.6,0.1,0.1]}}</code>
    <p class="s-note">{{ t('AI 只能建议目标，不能直接指挥飞机；未配置 TARGET_AI_API_KEY 时接口关闭（503）。也可用 "geo":{"lat","lon","height","heightRef"} 代替 image。') }}</p>
  </section>
</template>

<style scoped>
.api {
  gap: var(--sp-2);
}
.api .s-sub:not(:first-of-type) {
  margin-top: var(--sp-2);
}
.alt {
  color: var(--text-2, var(--muted));
  font-weight: 400;
}
.seg {
  align-self: flex-start;
}
</style>
