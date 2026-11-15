#ifndef FLIGHT_NODE_IDENTITY_H
#define FLIGHT_NODE_IDENTITY_H
#include <stdint.h>
/* Display/provisioning ID only. Zero means UNSET; MAC/boot remain identity. */
uint32_t node_identity_default(const uint8_t mac[6]);
#endif
