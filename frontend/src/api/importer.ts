import { api } from './http'
import type { Route, RouteRequest } from './routes'
import type { SafetyCheckResult } from './safety'

export interface ImportResult {
  format: string
  route: RouteRequest
  warnings: string[]
  safety: SafetyCheckResult
  saved: Route | null
}

export interface ImportParams {
  name?: string
  defaultHeight?: number | null
  takeoffAltitude?: number | null
  dryRun: boolean
}

/** R-17: upload a waypoint file (KMZ/WPML, GeoJSON, CSV); same pipeline and safety layer as the external API. */
export function importRouteFile(file: File, p: ImportParams): Promise<ImportResult> {
  const form = new FormData()
  form.append('file', file)
  if (p.name) form.append('name', p.name)
  if (p.defaultHeight != null) form.append('defaultHeight', String(p.defaultHeight))
  if (p.takeoffAltitude != null) form.append('takeoffAltitude', String(p.takeoffAltitude))
  form.append('dryRun', String(p.dryRun))
  return api<ImportResult>('/api/v1/routes/import', { method: 'POST', form })
}
