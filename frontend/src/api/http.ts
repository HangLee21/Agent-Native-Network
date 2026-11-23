import { config } from '@/config/runtime'
import { t, translateIncoming } from '@/i18n'

/** Error returned by the backend; `details` carries e.g. safety violations (HTTP 422). */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly details: unknown = null,
  ) {
    super(message)
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
  form?: FormData
  signal?: AbortSignal
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (opts.form) {
    body = opts.form
  } else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  let res: Response
  try {
    // no-store: never cached, and the browser does not hold a GET back while an earlier one to the same address is
    // still out (field test 2026-11-10: one stuck dog poll held every later one for about 10 s)
    res = await fetch(config().apiBaseUrl + path, { method: opts.method ?? 'GET', headers, body, signal: opts.signal, cache: 'no-store' })
  } catch {
    throw new ApiError(t('无法连接后端服务'), 0)
  }
  const text = await res.text()
  // backend text (reasons, alerts…) is Chinese; shown in English when the interface is (i18n/index.ts)
  const data: unknown = translateIncoming(text ? safeJson(text) : null)
  if (!res.ok) {
    const obj = (data ?? {}) as { message?: string; error?: string }
    throw new ApiError(obj.message || obj.error || t('请求失败（HTTP {status}）', { status: res.status }), res.status, data)
  }
  return data as T
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}
