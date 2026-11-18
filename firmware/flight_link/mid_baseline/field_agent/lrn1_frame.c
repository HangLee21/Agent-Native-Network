/* LRN1 frame builder: capacity-bounded rows plus two optional health blocks. */
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

/* 24 bytes. Bytes 19..23 stay zero for future fields. */
static void write_status(uint8_t* b, const lrn1_status* s) {
	b[0] = s->reset_reason;
	put(b + 1, s->supply_mv, 2);
	b[3] = (uint8_t)s->die_temp_c;
	b[4] = s->heap_free_kb;
	b[5] = s->queue_depth;
	b[6] = s->tx_drops;
	b[7] = s->routes;
	b[8] = (uint8_t)s->lora_tx_power_dbm;
	b[9] = s->lora_sf;
	b[10] = s->fault_flags;
	b[11] = s->pi_flags;
	b[12] = (uint8_t)s->pi_cpu_temp_c;
	b[13] = s->pi_load_x10;
	put(b + 14, s->pi_mem_free_mb, 2);
	b[16] = (uint8_t)s->pi_wifi_rssi;
	b[17] = s->serial_errors;
	b[18] = s->battery_pct;
}

/* 20 bytes. Bytes 18..19 stay zero. */
static void write_gps(uint8_t* b, const lrn1_gps* g) {
	b[0] = g->flags;
	put(b + 1, (uint32_t)g->lat_e7, 4);
	put(b + 5, (uint32_t)g->lon_e7, 4);
	put(b + 9, (uint16_t)g->alt_m, 2);
	put(b + 11, g->speed_cms, 2);
	put(b + 13, g->heading_cdeg, 2);
	b[15] = g->sats;
	b[16] = g->hdop_x10;
	b[17] = g->vdop_x10;
}

unsigned lrn1_build(nd_node* n, mt_node* m, uint64_t now, int (*allowed)(mid_id),
                    uint32_t node_number, const lrn1_status* st, const lrn1_gps* g,
                    uint8_t* data, unsigned cap, uint32_t seq, uint32_t period_ms,
                    uint32_t* cursor, lrn1_result* out) {
	unsigned max_rows = lrn1_capacity(cap, st != 0, g != 0);
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
	data[6] = (uint8_t)((rows < eligible ? LRN1_FLAG_TRUNCATED : 0u)
	                        | (n->full ? LRN1_FLAG_TABLE_FULL : 0u));
	if (st) data[6] |= LRN1_FLAG_STATUS;
	if (g) data[6] |= LRN1_FLAG_GPS;
	memcpy(data + 8, n->self.mac, 6);
	put(data + 14, n->boot, 4);
	put(data + 18, seq, 4);
	put(data + 22, now, 8);
	put(data + 30, n->group, 4);
	put(data + 36, period_ms, 4);      /* report period, as configured */
	put(data + 40, 0, 4);              /* tx delay: stamped by lrn1_set_delay() */
	/* Byte 35 carries the device number so the receiver can name a node without any roster
	 * file. Out-of-range values become 0 ("unassigned") instead of wrapping, which would
	 * silently claim somebody else's number. */
	data[35] = (uint8_t)(node_number >= 1u && node_number <= 255u ? node_number : 0u);
	data[7] = (uint8_t)rows;
	data[34] = (uint8_t)(eligible > 255 ? 255 : eligible);

	for (unsigned r = 0; r < rows; r++) write_row(data, r, &n->peers[chosen[r]], m, now);

	unsigned len = (unsigned)(LRN1_HEADER + LRN1_ROW * rows);
	if (st) { write_status(data + len, st); len += LRN1_STATUS; }
	if (g) { write_gps(data + len, g); len += LRN1_GPS; }
	len += LRN1_CRC;
	if (len > cap) return 0;
	put(data + len - 4, crc32(data, len - 4), 4);
	out->rows = rows;
	out->has_status = st != 0;
	out->has_gps = g != 0;
	return len;
}

void lrn1_set_delay(uint8_t* data, unsigned len, uint32_t delay_ms) {
	if (!data || len < LRN1_MIN_BYTES) return;
	data[6] |= LRN1_FLAG_DELAY_SET;
	put(data + 40, delay_ms, 4);
	put(data + len - 4, crc32(data, len - 4), 4);
}

/* Weak default: host tests and any build without an application override report 0
 * (unassigned). The firmware defines the real one from its NVS-backed number. */
__attribute__((weak)) uint32_t lrn1_node_number(void) { return 0u; }

/* Weak defaults: everything unknown. The firmware provides real values. */
__attribute__((weak)) void lrn1_platform_status(lrn1_status* s) { (void)s; }
__attribute__((weak)) int lrn1_platform_gps(lrn1_gps* g) { (void)g; return 0; }
