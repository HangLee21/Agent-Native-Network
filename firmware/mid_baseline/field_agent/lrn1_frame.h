#ifndef MID_LRN1_FRAME_H
#define MID_LRN1_FRAME_H
/* LRN1 frame builder, portable (no ESP-IDF dependency) so it can be host-tested.
 *
 * Layout (little endian):
 *   [0..44)   header
 *   [44..)    20-byte rows, `rows` of them
 *   optional  24-byte status block   when header byte 6 bit3 is set
 *   optional  20-byte GPS block      when header byte 6 bit4 is set
 *   last 4    CRC32 over everything before it
 *
 * The two optional blocks carry node and edge-node health without a format version bump:
 * the flags say whether they are present, so the decoder derives the length. They are sent
 * periodically rather than every frame, so neighbour rows stay full in dense clusters.
 *
 * The previous builder in lora_ref/runtime.c walked all ND_PEERS rows and wrote 20 bytes
 * each with no cap: with 9+ neighbours it wrote past the 208-byte frame buffer and over the
 * fields that follow it. This module enforces the capacity from the caller's buffer size.
 */
#include <stdint.h>
#include "neighbors.h"
#include "telemetry.h"

#define LRN1_MAGIC "LRN1"
#define LRN1_HEADER 44u
#define LRN1_ROW 20u
#define LRN1_STATUS 24u
#define LRN1_GPS 20u
#define LRN1_CRC 4u
#define LRN1_MIN_BYTES (LRN1_HEADER + LRN1_CRC)

/* Header byte 6 (flags). */
/* decoder.py treats bit0 as 'rows were dropped', so it must be set
 * whenever rows < eligible. Leaving it clear made every truncated frame
 * invalid on the legacy decode path. */
#define LRN1_FLAG_TRUNCATED 0x01u
#define LRN1_FLAG_TABLE_FULL 0x02u
#define LRN1_FLAG_DELAY_SET 0x04u
#define LRN1_FLAG_STATUS 0x08u
#define LRN1_FLAG_GPS 0x10u

/* Rows that fit in `cap` bytes once the optional blocks are accounted for. */
static inline unsigned lrn1_capacity(unsigned cap, int with_status, int with_gps) {
	unsigned fixed = LRN1_HEADER + LRN1_CRC
	                 + (with_status ? LRN1_STATUS : 0u)
	                 + (with_gps ? LRN1_GPS : 0u);
	return cap < fixed ? 0u : (cap - fixed) / LRN1_ROW;
}

/* Node and edge-node health. Field order is the wire order; keep it stable. */
typedef struct {
	uint8_t reset_reason;   /* LRN1_RST_* */
	uint16_t supply_mv;     /* node supply rail, millivolts (0 = unknown) */
	int8_t die_temp_c;      /* node die temperature (-128 = unknown) */
	uint8_t heap_free_kb;   /* free heap, KB, saturating */
	uint8_t queue_depth;
	uint8_t tx_drops;
	uint8_t routes;
	int8_t lora_tx_power_dbm;
	uint8_t lora_sf;
	uint8_t fault_flags;    /* LRN1_FAULT_* */
	uint8_t pi_flags;       /* LRN1_PI_* */
	int8_t pi_cpu_temp_c;
	uint8_t pi_load_x10;    /* 0..255 = 0.0..25.5 */
	uint16_t pi_mem_free_mb;
	int8_t pi_wifi_rssi;
	uint8_t serial_errors;
	uint8_t battery_pct;    /* 0 = unknown */
} lrn1_status;

#define LRN1_RST_UNKNOWN 0u
#define LRN1_RST_POWERON 1u
#define LRN1_RST_BROWNOUT 2u
#define LRN1_RST_WATCHDOG 3u
#define LRN1_RST_SOFTWARE 4u
#define LRN1_RST_PANIC 5u

#define LRN1_FAULT_UNDERVOLTAGE 0x01u
#define LRN1_FAULT_WATCHDOG 0x02u
#define LRN1_FAULT_TABLE_FULL 0x04u
#define LRN1_FAULT_THERMAL 0x08u

#define LRN1_PI_ALIVE 0x01u
#define LRN1_PI_NETWORK 0x02u
#define LRN1_PI_GPS_SOURCE 0x04u

/* GPS block. Reserved now: with no receiver the flags stay 0 and the viewer shows
 * "no fix" instead of plotting a bogus position at 0,0. */
typedef struct {
	uint8_t flags;          /* LRN1_GPS_* */
	int32_t lat_e7;         /* degrees * 1e7 */
	int32_t lon_e7;
	int16_t alt_m;
	uint16_t speed_cms;
	uint16_t heading_cdeg;  /* degrees * 100 */
	uint8_t sats;
	uint8_t hdop_x10;
	uint8_t vdop_x10;
} lrn1_gps;

#define LRN1_GPS_VALID 0x01u
#define LRN1_GPS_FIX_3D 0x02u
#define LRN1_GPS_DGNSS 0x04u

typedef struct {
	unsigned rows;      /* rows actually written */
	unsigned eligible;  /* neighbours that were eligible before truncation */
	int has_status;
	int has_gps;
} lrn1_result;

/* Builds one frame into `data` (capacity `cap`).
 *
 * `node_number` is the device's own display number (NVS-backed). It rides in header byte 35
 * so the gateway can learn "MAC -> number" from the air with no roster file.
 *
 * `st` and `g` may be NULL; passing them adds the corresponding block and sets its flag.
 * The caller decides the cadence (for example every 5th frame) so neighbour rows stay full.
 *
 * Row selection, in order of value to the gateway:
 *   1. every neighbour whose state is not BIDIRECTIONAL (lost/heard) - topology changes,
 *   2. the rest round-robin from `*cursor`, so with more neighbours than rows each one is
 *      still reported at least once every ceil(eligible / rows) frames.
 * `cursor` belongs to the caller and is advanced here; pass the same slot every time.
 * Returns the frame length, or 0 when it does not fit.
 */
unsigned lrn1_build(nd_node* n, mt_node* m, uint64_t now, int (*allowed)(mid_id),
                    uint32_t node_number, const lrn1_status* st, const lrn1_gps* g,
                    uint8_t* data, unsigned cap, uint32_t seq, uint32_t period_ms,
                    uint32_t* cursor, lrn1_result* out);

/* Stamps the actual transmit delay (frame flag bit 2) and refreshes the CRC. Used right
 * before handing the frame to the radio, when the real wait is known. */
void lrn1_set_delay(uint8_t* data, unsigned len, uint32_t delay_ms);

/* The device's node number, provided by the application. Weak default of 0 keeps this
 * module host-testable and free of ESP-IDF/app dependencies. */
uint32_t lrn1_node_number(void);

/* Platform hooks. Weak defaults leave every field zero, so host tests and boards without
 * the sensors still emit a valid frame. The firmware overrides them. */
void lrn1_platform_status(lrn1_status* s);
int lrn1_platform_gps(lrn1_gps* g);   /* returns 1 when a fix is available */

#endif
