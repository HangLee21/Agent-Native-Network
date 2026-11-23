#ifndef FLIGHT_RELIABLE_ROUTE_H
#define FLIGHT_RELIABLE_ROUTE_H
#include "reliable.h"
#include "source_route.h"
void fr_route_before(fr_state*,sr_node*,const uint8_t*,size_t,uint64_t);
void fr_route_submitted(fr_state*,const uint8_t*,size_t,uint32_t);
#endif
