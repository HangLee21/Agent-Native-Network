/**
 * The REST helper asks the browser not to cache: otherwise Chrome holds a GET back while an earlier one to the same
 * address is still out, and one stuck dog poll left the page without news for about 10 s (field test 2026-11-10).
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/http'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api()', () => {
  it('sends every request with cache: no-store', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response('{"ok":true}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await api('/api/v2/dogs')
    await api('/api/v2/dogs/x/commands', { method: 'POST', body: { a: 1 } })
    expect(fetchMock).toHaveBeenCalledTimes(2)
    for (const call of fetchMock.mock.calls) expect((call[1] as RequestInit).cache).toBe('no-store')
  })
})
