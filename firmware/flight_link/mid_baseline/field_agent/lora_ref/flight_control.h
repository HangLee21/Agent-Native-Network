#ifndef FLIGHT_CONTROL_H
#define FLIGHT_CONTROL_H
#include <stddef.h>
#include <stdint.h>

#define FC_FRAME 48u
#define FC_REPORTS 4u
#define FC_SEEN 16u

typedef struct { uint32_t seq; uint64_t sent_ms; uint8_t used; } fc_report;
typedef struct { uint8_t used, request[44], response[48]; uint64_t expires_ms; } fc_entry;
typedef struct {
    uint8_t mac[6]; uint32_t boot;
    fc_report reports[FC_REPORTS]; unsigned report_next;
    fc_entry entries[FC_SEEN];
    uint32_t executed, duplicates, rejected, full;
} fc_state;

void fc_init(fc_state *, const uint8_t mac[6], uint32_t boot);
void fc_report_sent(fc_state *, uint32_t seq, uint64_t sent_ms);
/* 1=execute new, 2=duplicate (no re-execution), 0=ignore/reject.
 * On 1 or 2 response contains 48 bytes ready for LoRa transmission. */
int fc_receive(fc_state *, const uint8_t *, size_t, uint64_t now_ms,
               uint32_t status_bits, uint8_t response[FC_FRAME]);
uint32_t fc_crc32(const uint8_t *, size_t);
#endif
