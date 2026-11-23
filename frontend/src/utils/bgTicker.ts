/**
 * A repeating timer that keeps its pace while the tab is in the background. Browsers slow page timers in hidden tabs
 * (Chrome: about once a second at once, about once a minute after five minutes), which would let the Lite3 idle
 * keep-alive lapse although the user decided background keeps control (2026-11-07). Timers inside a dedicated worker
 * are not slowed that way, so the beat comes from a tiny worker; where workers are not available (tests, strict
 * pages) it falls back to a normal interval.
 */
export interface Ticker {
  stop(): void
}

export function startTicker(fn: () => void, ms: number): Ticker {
  if (typeof Worker !== 'undefined' && typeof Blob !== 'undefined' && typeof URL?.createObjectURL === 'function') {
    try {
      const src = `let t=null;onmessage=(e)=>{clearInterval(t);if(e.data>0)t=setInterval(()=>postMessage(0),e.data)}`
      const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }))
      const w = new Worker(url)
      URL.revokeObjectURL(url)
      w.onmessage = () => fn()
      w.postMessage(ms)
      return {
        stop() {
          w.postMessage(0)
          w.terminate()
        },
      }
    } catch {
      /* worker refused (e.g. content security policy): fall back below */
    }
  }
  const id = window.setInterval(fn, ms)
  return { stop: () => window.clearInterval(id) }
}
