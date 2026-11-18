/* LRN1 frame builder: capacity-bounded, value-ordered row selection. */
#include <string.h>
#include "lrn1_frame.h"

static void put(uint8_t* p, uint64_t v, unsigned n) {
	for (unsigned i = 0; i < n; i++) p[i] = (uint8_t)(v >> (8 * i));
}

static uint32_t crc32(const uint8_t* p, unsigned n) {
	uint32_t crc = 0xffffffffu;
	while (n--) {
		crc ^= *p++;
		for (unsigned i = 0; i < 8; i++) crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
	}
	return ~crc;
}

static uint16_t age_of(uint64_t now, uint64_t at, unsigned cap) {
	return (uint16_t)(at > now || now - at >= cap ? cap : now - at + 1);
}

/* Writes one row; `slot` is the row index, already bounded by the caller. */
static void write_row(uint8_t* base, unsigned slot, const nd_peer* p, const mt_node* m,
                      uint64_t now) {
	uint8_t* r = base + LRN1_HEADER + LRN1_ROW * slot;
	memcpy(r, p->id.mac, 6);
	put(r + 6, p->boot, 4);
	r[10] = (uint8_t)nd_state((nd_peer*)p, now);
	put(r + 12, age_of(now, p->seen, 12000), 2);
	if (p->confirmed) {
		r[11] |= 1;
		put(r + 14, age_of(now, p->ack, 9000), 2);
	}
	for (unsigned k = 0; k < MT_ROWS; k++) {
		const mt_rf* rf = &m->rf[k];
		if (!rf->used || !mid_equal(rf->peer, p->id) || rf->at > now) continue;
		r[11] |= 4;
		put(r + 17, age_of(now, rf->at, 12000), 2);
		if (rf->rssi_valid) { r[11] |= 2; r[16] = (uint8_t)(int8_t)rf->rssi; }
		if (rf->channel_valid) { r[11] |= 8; r[19] = (uint8_t)rf->channel; }
		break;
	}
}

unsigned lrn1_build(nd_node* n, mt_node* m, uint64_t now, int (*allowed)(mid_id),
                    uint32_t node_number, uint8_t* data, unsigned cap, uint32_t seq,
                    uint32_t period_ms, uint32_t* cursor, lrn1_result* out) {
	unsigned max_rows = lrn1_capacity(cap);
	if (!data || !out || !max_rows) return 0;
	memset(data, 0, cap);

	/* Eligible neighbours, in table order. */
	unsigned idx[ND_PEERS], eligible = 0;
	for (unsigned i = 0; i < ND_PEERS; i++) {
		nd_peer* p = &n->peers[i];
		if (!p->used || !p->boot) continue;
		if (allowed && !allowed(p->id)) continue;
		idx[eligible++] = i;
	}
	out->eligible = eligible;

	/* Pass 1: anything that is not currently BIDIRECTIONAL carries a topology change. */
	unsigned chosen[ND_PEERS], rows = 0;
	for (unsigned k = 0; k < eligible && rows < max_rows; k++) {
		if (nd_state(&n->peers[idx[k]], now) != 2) chosen[rows++] = idx[k];
	}
	/* Pass 2: round-robin the remainder so every neighbour is reported eventually. */
	if (rows < max_rows && eligible) {
		unsigned start = cursor ? (*cursor % eligible) : 0u;
		unsigned taken = 0;
		for (unsigned k = 0; k < eligible && rows < max_rows; k++) {
			unsigned slot = idx[(start + k) % eligible];
			int dup = 0;
			for (unsigned r = 0; r < rows; r++) if (chosen[r] == slot) { dup = 1; break; }
			if (dup) continue;
			chosen[rows++] = slot;
			taken = k + 1;
		}
		if (cursor) *cursor = (start + (taken ? taken : 1u)) % eligible;
	}

	memcpy(data, LRN1_MAGIC, 4);
	data[4] = (uint8_t)LRN1_HEADER;
	data[5] = (uint8_t)LRN1_ROW;
	data[6] = n->full ? 2 : 0;
	memcpy(data + 8, n->self.mac, 6);
	put(data + 14, n->boot, 4);
	put(data + 18, seq, 4);
	put(data + 22, now, 8);
	put(data + 30, n->group, 4);
	put(data + 36, period_ms, 4);      /* report period, as configured */
	put(data + 40, 0, 4);              /* tx delay: stamped by lrn1_set_delay() */
	/* Byte 35 was unused; it now carries the device number so the receiver can name a node
	 * without any roster file. Out-of-range values fall back to 0 ("unassigned") instead of
	 * wrapping, which would silently claim somebody else's number. */
	data[35] = (uint8_t)(node_number >= 1u && node_number <= 255u ? node_number : 0u);
	data[7] = (uint8_t)rows;
	data[34] = (uint8_t)(eligible > 255 ? 255 : eligible);

	for (unsigned r = 0; r < rows; r++) write_row(data, r, &n->peers[chosen[r]], m, now);

	unsigned len = (unsigned)(LRN1_HEADER + LRN1_ROW * rows + LRN1_CRC);
	if (len > cap) return 0;
	put(data + len - 4, crc32(data, len - 4), 4);
	out->rows = rows;
	return len;
}

void lrn1_set_delay(uint8_t* data, unsigned len, uint32_t delay_ms) {
	if (!data || len < LRN1_MIN_BYTES) return;
	data[6] |= 4;
	put(data + 40, delay_ms, 4);
	put(data + len - 4, crc32(data, len - 4), 4);
}

/* Weak default: host tests and any build without an application override report 0
 * (unassigned). The firmware defines the real one from its NVS-backed number. */
__attribute__((weak)) uint32_t lrn1_node_number(void) { return 0u; }
