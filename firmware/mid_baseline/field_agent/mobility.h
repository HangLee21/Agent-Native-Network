#ifndef MID_MOBILITY_H
#define MID_MOBILITY_H
/* Mobility State + link lifetime prediction (phase 1, shadow mode only).
 *
 * This module never decides routing. It keeps a per-neighbour mobility cache, predicts
 * the geometric time until the pair leaves a configured range, quantifies the
 * uncertainty of that prediction, and exposes a link-risk state with hysteresis.
 * The caller may only log the result (shadow mode) in this phase.
 *
 * Units are integer to keep the wire format and tests exact:
 *   position  : 1e-7 degrees (lat/lon), millimetres (altitude)
 *   velocity  : millimetres/second, east/north/up
 *   time      : milliseconds, monotonic
 * A velocity of 0 with valid=0 means "unknown", never "stationary".
 */
#include <stddef.h>
#include <stdint.h>
#include "mid.h"

#define MOB_ROWS 32u
#define MOB_LET_INFINITE 0x7fffffff
/* Risk thresholds: geometric headroom below which a link is reported as risky. */
#define MOB_DEGRADE_MS 8000
#define MOB_CRITICAL_MS 3000
/* A risk change must persist this long before it is published (anti-flapping). */
#define MOB_HYSTERESIS_MS 2000u
/* Below this confidence the estimate is inconclusive rather than risky: with a small
 * relative speed the position error alone dominates the predicted lifetime, and calling
 * that "about to break" makes a stable formation oscillate. */
#define MOB_MIN_CONFIDENCE 300u
/* Geometric range used for the prediction, until a measured R_eff replaces it. */
#define MOB_RANGE_DEFAULT_MM 120000

enum { MOB_NO_FIX = 0, MOB_FIX_2D = 1, MOB_FIX_3D = 2 };
enum { MOB_SRC_UNAVAILABLE = 0, MOB_SRC_GNSS = 1, MOB_SRC_INJECTED = 2, MOB_SRC_REPLAY = 3 };
enum { MOB_MODE_UNKNOWN = 0, MOB_MODE_HOVER = 1, MOB_MODE_CRUISE = 2, MOB_MODE_TRANSIT = 3 };
enum { MOB_RISK_GOOD = 0, MOB_RISK_DEGRADING = 1, MOB_RISK_AT_RISK = 2 };

typedef struct {
	uint32_t valid;          /* bit0 position, bit1 velocity, bit2 accuracy */
	int32_t lat_e7, lon_e7, alt_mm;
	int32_t ve_mm_s, vn_mm_s, vu_mm_s;
	uint32_t accuracy_mm, velocity_accuracy_mm_s;
	uint32_t sample_ms;      /* when the source measured this state */
	uint8_t fix, source, flight_mode;
} mob_state;

typedef struct {
	uint32_t ewma_pdr;       /* 0..1000, EWMA of delivery success */
	uint32_t etx_x100;       /* 100..10000, 100 = perfect */
	uint32_t samples;
	uint32_t last_rssi;      /* dBm encoded as int32 cast to uint32, 0 = unknown */
} mob_link;

typedef struct {
	int used;
	mid_id peer;
	mob_state remote;
	mob_link link;
	uint64_t received_ms;
	uint32_t updates, stale_rejects;
	/* Prediction, recomputed on demand. */
	int32_t let_ms, let_low_ms, let_high_ms;
	uint32_t confidence;     /* 0..1000 */
	uint32_t distance_mm, closing_mm_s;   /* closing > 0 means approaching */
	uint8_t risk, risk_target;
	uint64_t risk_since;
} mob_peer;

typedef struct {
	mob_state self;
	mob_peer peers[MOB_ROWS];
	uint32_t range_mm;
	/* Risk thresholds must be derived from the range and the fleet speed: with
	 * R = 120 m the shortest possible lifetime is 2R/|u|, so an absolute constant
	 * can be unreachable at realistic closing speeds. */
	uint32_t degrade_ms, critical_ms;
	uint32_t updates, rejects, overflows;
	uint32_t predictions, risk_changes;
} mob_node;

void mob_init(mob_node*, uint32_t range_mm);
/* Override the risk thresholds derived from range and fleet speed. */
void mob_limits(mob_node*, uint32_t degrade_ms, uint32_t critical_ms);
/* Local state. Returns 0 on success, -1 on invalid input. */
int mob_self(mob_node*, const mob_state*, uint64_t now_ms);
/* Neighbour state. A newer sample_ms always wins; an older one is counted and dropped. */
int mob_peer_update(mob_node*, mid_id peer, const mob_state*, uint64_t now_ms);
/* Delivery observation in permille, used to keep an ETX-style link weight. */
int mob_delivery(mob_node*, mid_id peer, int delivered, int rssi_dbm, uint64_t now_ms);
/* Recompute prediction and risk for one peer. Safe to call repeatedly. */
int mob_predict(mob_node*, mob_peer*, uint64_t now_ms);
/* Recompute every known peer; returns the number predicted. */
unsigned mob_predict_all(mob_node*, uint64_t now_ms);
/* Shadow record, one line without newline. Returns length or -1 when it does not fit. */
int mob_shadow_line(const mob_node*, const mob_peer*, uint64_t now_ms, char* out, size_t cap);
int mob_self_line(const mob_node*, uint64_t now_ms, char* out, size_t cap);
/* 0 GOOD, 1 DEGRADING, 2 AT_RISK. */
const char* mob_risk_name(unsigned risk);
const char* mob_source_name(unsigned source);
#endif
