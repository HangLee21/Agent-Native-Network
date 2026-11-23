/**
 * Click mapping for target selection (D-21): the player shows the stream with `object-fit: contain`,
 * so a click is mapped to the video frame, not the panel; clicks on the black bars are ignored.
 * Results are normalised 0..1 from the top-left of the frame, as drc_camera_aim / frame_zoom expect.
 */
export interface FrameRect {
  left: number
  top: number
  width: number
  height: number
}

/** Visible frame inside an element of size (ew, eh) for a video of size (vw, vh); vw/vh = 0 means it fills the element. */
export function frameRect(ew: number, eh: number, vw: number, vh: number): FrameRect {
  if (!(vw > 0) || !(vh > 0) || !(ew > 0) || !(eh > 0)) return { left: 0, top: 0, width: ew, height: eh }
  const scale = Math.min(ew / vw, eh / vh)
  const width = vw * scale
  const height = vh * scale
  return { left: (ew - width) / 2, top: (eh - height) / 2, width, height }
}

/** Element-relative point → normalised frame point, or null when it lies on the bars. */
export function toFrame(px: number, py: number, r: FrameRect): { x: number; y: number } | null {
  const x = (px - r.left) / r.width
  const y = (py - r.top) / r.height
  if (x < 0 || x > 1 || y < 0 || y > 1) return null
  return { x, y }
}

/** Two element-relative corners → normalised box clamped to the frame (x, y = top-left), or null when empty. */
export function toFrameBox(ax: number, ay: number, bx: number, by: number, r: FrameRect): { x: number; y: number; w: number; h: number } | null {
  const clamp = (v: number) => Math.max(0, Math.min(1, v))
  const x1 = clamp((Math.min(ax, bx) - r.left) / r.width)
  const x2 = clamp((Math.max(ax, bx) - r.left) / r.width)
  const y1 = clamp((Math.min(ay, by) - r.top) / r.height)
  const y2 = clamp((Math.max(ay, by) - r.top) / r.height)
  if (x2 - x1 < 0.01 || y2 - y1 < 0.01) return null
  return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }
}

/** Frame size of the synthetic mock video (16:9, same aspect the simulator's camera model assumes). */
export const MOCK_FRAME = { w: 1920, h: 1080 }

/** A drag shorter than this many pixels counts as a tap. */
export const TAP_SLOP_PX = 6
