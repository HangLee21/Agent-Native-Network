import { describe, expect, it, vi } from 'vitest'
import { importRouteFile } from '@/api/importer'
import { setConfigForTest } from '@/config/runtime'

describe('file import (R-17)', () => {
  it('posts multipart form data with options to the import endpoint', async () => {
    setConfigForTest({ apiBaseUrl: 'http://api.test', wsUrl: '', map: { coordSys: 'WGS84', tileUrl: '', subdomains: '', attribution: '', maxZoom: 19, apiKey: '' } })
    let captured: { url: string; body: FormData } | null = null
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      captured = { url, body: init.body as FormData }
      return new Response(JSON.stringify({ format: 'CSV', route: { name: 'x', waypoints: [] }, warnings: [], safety: { passed: true, violations: [] }, saved: null }))
    }))
    const r = await importRouteFile(new File(['22.58,113.94,40'], 'p.csv'), { name: 'A', defaultHeight: 50, takeoffAltitude: null, dryRun: true })
    expect(r.format).toBe('CSV')
    expect(captured!.url).toBe('http://api.test/api/v1/routes/import')
    expect(captured!.body.get('dryRun')).toBe('true')
    expect(captured!.body.get('defaultHeight')).toBe('50')
    expect(captured!.body.get('takeoffAltitude')).toBeNull()
    vi.unstubAllGlobals()
  })
})
