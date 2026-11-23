import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { lang, t } from '@/i18n'
import { droneGroups } from '@/components/drone/infoFields'
import SaveBar from '@/components/settings/SaveBar.vue'

afterEach(() => {
  lang.value = 'zh'
})

describe('settings, info panel and chips in English', () => {
  it('labels the telemetry groups and values in English', () => {
    lang.value = 'en'
    const groups = droneGroups(null, null)
    expect(groups.map((g) => g.title)).toContain('Flight status')
    const limits = groups.find((g) => g.title === 'Limits & safety')
    expect(limits?.rows.map((r) => r.label)).toContain('Aircraft altitude limit')
  })

  it('writes the save bar summary with English word order and plurals', () => {
    lang.value = 'en'
    const w = mount(SaveBar, { props: { title: 'Targets & AI', names: ['Stop distance', 'AI orbit'], saveLabel: 'Save', saveTest: 's', dirty: true, saving: false } })
    expect(w.text()).toContain('Targets & AI: 2 unsaved changes')
    expect(w.text()).toContain('Stop distance, AI orbit')
    expect(w.text()).toContain('Discard changes')
  })

  it('keeps the Chinese save bar exactly as before', () => {
    const w = mount(SaveBar, { props: { title: '目标选择与 AI', names: ['停止距离'], saveLabel: '保存', saveTest: 's', dirty: true, saving: false } })
    expect(w.text()).toContain('目标选择与 AI 有 1 项未保存')
  })

  it('builds the proximity line from whole clauses', () => {
    lang.value = 'en'
    const line = t('{a} 与 {b}：水平 {h} m · {v}{stale}{stopping}{stopped}', {
      a: 'M4E-1', b: 'M4E-2', h: 12, v: t('高度差 {n} m', { n: 3 }), stale: '', stopping: '',
      stopped: t('，已让 {names} 悬停', { names: ['M4E-1', 'M4E-2'].join(t('、')) }),
    })
    expect(line).toBe('M4E-1 and M4E-2: horizontal 12 m · vertical 3 m; M4E-1, M4E-2 told to hover')
  })
})
