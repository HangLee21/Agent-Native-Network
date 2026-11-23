<script setup lang="ts">
import NetworkView from '@/views/NetworkView.vue'
import { useSystemStore } from '@/stores/system'
import { isEn, setLang, t } from '@/i18n'
import mark from '@/assets/brand/embonet-mark-color.svg'
withDefaults(defineProps<{ workspace?: 'real' | 'mock' }>(), { workspace: 'real' })
const system = useSystemStore()
system.applyTheme(system.theme)
</script>
<template>
  <div class="studio-shell" :class="{ 'demo-shell': workspace === 'mock' }">
    <div v-if="workspace === 'mock'" class="demo-ribbon" data-test="mock-entry">MOCK · {{ t('独立模拟演示 · 不含实机数据') }} <a href="/studio.html">{{ t('离开演示，进入真实工作区') }} ↗</a></div>
    <header class="studio-header"><a class="studio-brand" href="/studio.html" aria-label="EmboNet Studio"><img :src="mark" alt="" width="29" height="32"><span>Embo<span class="brand-accent">Net</span></span><small>STUDIO</small></a><nav :aria-label="t('页面')"><span class="active">{{ t('网络观测') }}</span><a v-if="workspace === 'real'" href="/#/network">{{ t('平台集成视图') }} ↗</a><a v-else href="/studio.html">{{ t('真实数据工作区') }} ↗</a></nav><div class="studio-tools"><span class="local-badge">{{ workspace === 'mock' ? 'MOCK / SYNTHETIC' : t('真实数据工作区') }}</span><button :aria-label="t('切换界面语言')" @click="setLang(isEn() ? 'zh' : 'en')">{{ isEn() ? t('中文') : 'EN' }}</button><button :aria-label="t('切换主题')" @click="system.applyTheme(system.theme === 'dark' ? 'outdoor' : 'dark')">{{ system.theme === 'dark' ? '☀' : '☾' }}</button></div></header>
    <main><NetworkView :workspace="workspace" /></main>
  </div>
</template>
<style scoped>
.demo-shell{border:3px solid #d39b42}.demo-ribbon{display:flex;justify-content:space-between;gap:12px;flex:none;background:#9c6415;color:white;padding:9px 24px;font-weight:700;font-size:12px;letter-spacing:.5px}.demo-ribbon a{color:white}.demo-shell .studio-brand small{color:#e3b35f}@media(max-width:600px){.demo-ribbon{padding:8px 10px;font-size:10px;flex-wrap:wrap}}
.studio-shell{height:100%;display:flex;flex-direction:column}.studio-header{display:flex;align-items:center;gap:42px;flex:none;min-height:64px;padding:0 30px;background:var(--panel);border-bottom:1px solid var(--border)}.studio-brand{display:flex;gap:9px;align-items:center;text-decoration:none;color:var(--text);font-size:21px;font-weight:600;letter-spacing:-.6px}.brand-accent{color:#39b8b0}.studio-brand small{font:9px var(--font-num);color:var(--text-dim);letter-spacing:2px;margin-left:6px}.studio-header nav{display:flex;align-self:stretch;align-items:center;gap:28px;font-size:12px}.studio-header nav a{color:var(--text-dim);text-decoration:none}.studio-header nav span{display:flex;align-items:center;height:100%;border-bottom:2px solid #42b9b0;color:var(--text)}.studio-tools{margin-left:auto;display:flex;align-items:center;gap:8px}.studio-tools button{background:transparent;color:var(--text-dim);border:1px solid var(--border);border-radius:5px;font:11px var(--font-ui);min-width:30px;height:29px;cursor:pointer}.local-badge{color:var(--text-dim);font-size:10px;margin-right:10px}.studio-shell main{flex:1;min-height:0}@media(max-width:850px){.studio-header{gap:25px;padding:0 18px}.local-badge,.studio-brand small{display:none}.studio-header nav{gap:15px;font-size:11px}}@media(max-width:520px){.studio-header{padding:0 12px;gap:16px;min-height:58px}.studio-brand{font-size:18px}.studio-header nav a{display:none}.studio-header nav{font-size:10px}.studio-brand img{width:23px}}
</style>
