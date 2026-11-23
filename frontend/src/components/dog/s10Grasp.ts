/**
 * Visual grasp state shared by the main view (photo, picking the target) and the grasp card (steps 1–4).
 * Snapshot valid 90 s, solution valid 30 s (interface document: solve / arm_plan).
 */
import { reactive } from 'vue'

export interface GraspSolution {
  ok: boolean
  planId: string | null
  jointsDeg: number[] | null
  depthM: number | null
  errorM: number | null
  targetM: number[] | null
  reason: string | null
}

export const grasp = reactive({
  /** Picking mode on the main view (the hold-to-move pad is hidden meanwhile). */
  selecting: false,
  snapshot: null as string | null,
  image: null as string | null,
  width: 640,
  height: 480,
  snapAt: 0,
  u: null as number | null,
  v: null as number | null,
  solution: null as GraspSolution | null,
  solvedAt: 0,
  radishImage: false,
})

export function resetGrasp(): void {
  grasp.selecting = false
  grasp.snapshot = null
  grasp.image = null
  grasp.snapAt = 0
  grasp.u = null
  grasp.v = null
  grasp.solution = null
  grasp.solvedAt = 0
}

/** Map coordinates typed on the navigation page; "set initial pose" uses the same values, as on the dog page. */
export const navGoal = reactive({ x: 0, y: 0, deg: 0 })
