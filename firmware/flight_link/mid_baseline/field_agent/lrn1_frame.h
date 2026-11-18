#ifndef MID_LRN1_FRAME_H
#define MID_LRN1_FRAME_H
/* LRN1 frame builder, portable (no ESP-IDF dependency) so it can be host-tested.
 *
 * The previous builder in lora_ref/runtime.c walked all ND_PEERS rows and wrote 20 bytes
 * each with no cap: with 9+ neighbours it wrote past the 208-byte frame buffer and over the
 * fields that follow it. This module enforces the capacity from the caller's buffer size and
 * chooses which rows to keep.
 */
#include <stdint.h>
#include "neighbors.h"
#include "telemetry.h"

#define LRN1_MAGIC "LRN1"
#define LRN1_HEADER 44u
#define LRN1_ROW 20u
#define LRN1_CRC 4u
#define LRN1_MIN_BYTES (LRN1_HEADER + LRN1_CRC)
/* Rows that fit in `cap` bytes. */
static inline unsigned lrn1_capacity(unsigned cap) {
	return cap < LRN1_MIN_BYTES ? 0u : (cap - LRN1_HEADER - LRN1_CRC) / LRN1_ROW;
}

typedef struct {
	unsigned rows;      /* rows actually written */
	unsigned eligible;  /* neighbours that were eligible before truncation */
} lrn1_result;

/* Builds one frame into `data` (capacity `cap`).
 *
 * `node_number` is the device's own display number (NVS-backed, set with node_id_set). It
 * rides in header byte 35 so the gateway can learn "MAC -> number" from the air and no
 * roster file has to be maintained. 0 means "not assigned"; values above 255 are clamped
 * to 0 rather than truncated, so a mis-set number never collides with a real one.
 *
 * Row selection, in order of value to the gateway:
 *   1. every neighbour whose state is not BIDIRECTIONAL (lost/heard) - topology changes,
 *   2. the rest round-robin from `*cursor`, so with more neighbours than rows each one is
 *      still reported at least once every ceil(eligible / rows) frames.
 * `cursor` belongs to the caller and is advanced here; pass the same slot every time.
 * Returns the frame length, or 0 when it does not fit.
 */
unsigned lrn1_build(nd_node* n, mt_node* m, uint64_t now, int (*allowed)(mid_id),
                    uint32_t node_number, uint8_t* data, unsigned cap, uint32_t seq,
                    uint32_t period_ms, uint32_t* cursor, lrn1_result* out);

/* The device's node number, provided by the application. Weak default of 0 keeps this
 * module host-testable and free of ESP-IDF/app dependencies. */
uint32_t lrn1_node_number(void);

/* Stamps the actual transmit delay (frame flag bit 2) and refreshes the CRC. Used right
 * before handing the frame to the radio, when the real wait is known. */
void lrn1_set_delay(uint8_t* data, unsigned len, uint32_t delay_ms);

#endif
