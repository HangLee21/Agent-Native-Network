#ifndef FLIGHT_RELIABLE_H
#define FLIGHT_RELIABLE_H
#include <stddef.h>
#include <stdint.h>
#ifndef MID_ROUTE_FEEDBACK
#define MID_ROUTE_FEEDBACK 0
#endif
#define FR_HEADER 32u
#define FR_CRC 4u
#define FR_MAX_PAYLOAD 124u
#define FR_PENDING 8u
#define FR_SEEN 32u
#define FR_RETRY_MS 350u
#define FR_LOCAL_RETRY_MS 100u
#define FR_LIFETIME_MS (3u*FR_RETRY_MS)
#define FR_SEEN_MS 30000u
typedef struct {uint8_t used,dst[6],len,attempts,local_rejections;
#if MID_ROUTE_FEEDBACK
 uint8_t feedback_done;
#endif
 uint8_t payload[FR_MAX_PAYLOAD];uint32_t id,dst_boot;
#if MID_ROUTE_FEEDBACK
 uint32_t first_route_seq;
#endif
 uint64_t due,deadline;} fr_pending;
typedef struct {uint8_t used,src[6],len,payload[FR_MAX_PAYLOAD];uint32_t origin_boot,id;uint64_t until;} fr_seen;
typedef struct {uint8_t self[6];uint32_t boot,next_id,delivered,timeouts,duplicates,rejected,seen_full,local_submit_failures;fr_pending pending[FR_PENDING];fr_seen seen[FR_SEEN];} fr_state;
typedef struct {uint8_t src[6],dst[6],payload[FR_MAX_PAYLOAD],submissions,local_rejections;uint32_t origin_boot,dst_boot,id;
#if MID_ROUTE_FEEDBACK
 uint32_t route_seq;
#endif
 uint16_t len;} fr_message;
typedef int (*fr_send_fn)(void*,const uint8_t dst[6],const uint8_t*,size_t);
typedef void (*fr_timeout_fn)(void*,const fr_message*);
void fr_init(fr_state*,const uint8_t self[6],uint32_t boot);
int fr_start(fr_state*,const uint8_t dst[6],uint32_t dst_boot,const uint8_t*,size_t,uint64_t,uint32_t*);
void fr_tick(fr_state*,uint64_t,fr_send_fn,fr_timeout_fn,void*);
/* 0 non-FLW2, -1 invalid, 1 first data, 2 duplicate data, 3 matched ACK,
 * 4 well-formed unmatched ACK. 1/2 return a bounded ACK in ack/ack_len. */
int fr_receive(fr_state*,const uint8_t outer_src[6],uint32_t outer_boot,
               const uint8_t*,size_t,uint64_t,fr_message*,uint8_t ack[160],size_t*ack_len);
#endif
