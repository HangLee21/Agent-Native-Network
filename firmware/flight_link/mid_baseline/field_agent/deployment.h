#ifndef MID_DEPLOYMENT_H
#define MID_DEPLOYMENT_H
#include "mid.h"
#define MID_DEPLOYMENT_BYTES 210u
typedef struct {
    char profile_id[65];
    uint8_t autostart;
    mid_table table;
} mid_deployment;
/* Deterministic directed paths only. Every configured row must reach its destination. */
int mid_deployment_validate(const mid_deployment *p, mid_id self);
int mid_deployment_encode(const mid_deployment *p, mid_id self, uint8_t *out, size_t cap);
int mid_deployment_decode(mid_deployment *p, mid_id self, const uint8_t *in, size_t len);
/* No publisher, publisher_boot or config flood is involved in this local mode. */
int mid_deployment_install(mid_node *node, const mid_deployment *p, mid_id self, uint64_t now);
#endif
