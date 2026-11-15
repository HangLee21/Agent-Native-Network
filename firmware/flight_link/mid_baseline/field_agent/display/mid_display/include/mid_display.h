#ifndef MID_DISPLAY_H
#define MID_DISPLAY_H
#include <stddef.h>
#include <stdint.h>

#define MID_DISPLAY_API_VERSION 4u
#define MID_DISPLAY_FRAME_BYTES 1024u
#define MID_DISPLAY_PAGE_COUNT 6u
#define MID_DISPLAY_COLS 21u
#define MID_DISPLAY_HELP_LINES 5u

typedef enum { MID_DISPLAY_MID=1, MID_DISPLAY_ANN=2 } mid_display_protocol;
typedef enum { MID_DISPLAY_IDLE, MID_DISPLAY_ARMED, MID_DISPLAY_ACTIVE,
               MID_DISPLAY_BENCH, MID_DISPLAY_WAIT_CONFIG } mid_display_mode;
enum { MID_DISPLAY_REF_ORIGIN=1, MID_DISPLAY_REF_BOOT=2,
       MID_DISPLAY_REF_SEQ=4, MID_DISPLAY_REF_FLOW=8 };
typedef struct {
    uint8_t origin[6];
    uint8_t valid; /* Presence mask. A numeric zero remains a valid value. */
    uint32_t boot, seq, flow;
} mid_display_ref;
typedef struct {
    uint8_t mac[6], channel;
    char label; /* A..E only for a physically registered MAC, otherwise '?'. */
    uint32_t node_id; /* Display/provisioning ID; 0 means UNSET. */
    mid_display_protocol protocol;
} mid_display_identity;
typedef enum {
    MID_DISPLAY_TX_NONE, MID_DISPLAY_TX_QUEUED, MID_DISPLAY_TX_SUBMITTED,
    MID_DISPLAY_TX_LINK_OK, MID_DISPLAY_TX_LINK_FAIL, MID_DISPLAY_TX_LOCAL_FAIL,
    MID_DISPLAY_TX_TIMEOUT, MID_DISPLAY_TX_ANN_CONFIRMED
} mid_display_tx_state;
typedef enum { MID_DISPLAY_RX_NONE, MID_DISPLAY_RX_RELAY,
               MID_DISPLAY_RX_DEST, MID_DISPLAY_RX_DUPLICATE } mid_display_rx_state;
typedef enum { MID_DISPLAY_CFG_NONE, MID_DISPLAY_CFG_RECEIVED,
               MID_DISPLAY_CFG_APPLIED, MID_DISPLAY_CFG_STALE,
               MID_DISPLAY_CFG_REJECTED } mid_display_cfg_state;
enum { MID_DISPLAY_CFG_ORIGIN=1, MID_DISPLAY_CFG_SEQ=2 };
typedef struct {
    uint32_t queued, submitted, link_ok, link_fail, local_fail, timeouts;
    uint32_t rx_dest, rx_relay, rx_duplicate, ann_confirmed;
    uint32_t cfg_received, cfg_applied, cfg_stale, cfg_rejected, invalid_events;
    uint32_t commands_ok, commands_error;
} mid_display_counts;
typedef struct {
    mid_display_identity identity;
    mid_display_mode mode;
    uint64_t at_ms;
    uint16_t peers, routes;
    mid_display_tx_state tx_state;
    mid_display_ref tx_ref;
    uint8_t tx_dst[6], tx_next[6]; /* All zero means not known, not broadcast. */
    mid_display_rx_state rx_state;
    mid_display_ref rx_ref;
    uint8_t rx_dst[6];
    mid_display_cfg_state cfg_state;
    uint8_t cfg_origin[6];
    uint8_t cfg_valid;
    uint32_t cfg_seq;
    mid_display_counts counts;
    uint32_t fault_count; /* Saturating, retained across command/config/RX success. */
    mid_display_tx_state last_fault;
    mid_display_ref fault_ref;
    int32_t fault_code;
    char command[12];
    int8_t command_result; /* 0 unknown, 1 accepted, -1 rejected. */
    char help[MID_DISPLAY_HELP_LINES][MID_DISPLAY_COLS+1]; /* E1 owns actual CLI text. */
    /* Last business packet. Control/status events never replace it. */
    mid_display_ref business_ref;
    uint8_t business_dst[6], business_next[6];
    uint8_t business_flags; /* RX=1, SUBMITTED=2, LINK_OK=4, FAIL=8, QUEUED=16, DEST=32. */
    mid_display_tx_state business_tx;
    uint64_t business_at_ms;
    uint8_t field_rf_peer[6],field_rf_valid,field_running;
    int16_t field_rssi;uint64_t field_rf_at;
    uint32_t field_tx,field_forward,field_rx,field_segment;
} mid_display_snapshot;
typedef enum {
    MID_DISPLAY_EV_STATUS=1, MID_DISPLAY_EV_COMMAND,
    MID_DISPLAY_EV_TX_QUEUED, MID_DISPLAY_EV_TX_SUBMITTED,
    MID_DISPLAY_EV_TX_LINK_OK, MID_DISPLAY_EV_TX_LINK_FAIL,
    MID_DISPLAY_EV_TX_LOCAL_FAIL, MID_DISPLAY_EV_TX_TIMEOUT,
    MID_DISPLAY_EV_ANN_CONFIRMED,
    MID_DISPLAY_EV_RX_RELAY, MID_DISPLAY_EV_RX_DEST, MID_DISPLAY_EV_RX_DUPLICATE,
    MID_DISPLAY_EV_CFG_RECEIVED, MID_DISPLAY_EV_CFG_APPLIED,
    MID_DISPLAY_EV_CFG_STALE, MID_DISPLAY_EV_CFG_REJECTED
} mid_display_event_kind;
typedef struct {
    mid_display_event_kind kind;
    uint64_t at_ms;
    mid_display_ref ref;
    uint8_t dst[6], next_hop[6];
    uint8_t cfg_origin[6];
    uint8_t cfg_valid;
    uint32_t cfg_seq;
    int32_t code;
    mid_display_mode mode;
    uint16_t peers, routes;
    char command[12];
    uint8_t command_ok;
} mid_display_event;

/* Pure C model, owned by one normal task. No radio, serial, heap or timers. */
char mid_display_registered_label(const uint8_t mac[6]);
int mid_display_model_init(mid_display_snapshot *s,const mid_display_identity *identity);
int mid_display_model_apply(mid_display_snapshot *s,const mid_display_event *event);
int mid_display_validate(const mid_display_snapshot *snapshot);
int mid_display_set_help(mid_display_snapshot *s,const char *const lines[MID_DISPLAY_HELP_LINES]);
const char *mid_display_tx_text(mid_display_tx_state state);
const char *mid_display_rx_text(mid_display_rx_state state);
const char *mid_display_cfg_text(mid_display_cfg_state state);
const char *mid_display_destination_text(const mid_display_snapshot *s);
/* Produces exactly 8x21 padded characters. Includes 2 text rows for the scaled title. */
void mid_display_lines(const mid_display_snapshot *s,unsigned page,char lines[8][MID_DISPLAY_COLS+1]);
void mid_display_render(const mid_display_snapshot *s,unsigned page,uint8_t frame[MID_DISPLAY_FRAME_BYTES]);

typedef enum { MID_DISPLAY_HW_OFF, MID_DISPLAY_HW_STARTING,
               MID_DISPLAY_HW_READY, MID_DISPLAY_HW_FAILED } mid_display_hw_state;
/* ESP-IDF v5.5.1 / EoRa-HUB-400TB only. Single producer task; never call from ISR.
 * start() returns 0 when a worker was created, not when pixels are verified.
 * publish() copies a snapshot with zero queue wait. Hardware errors affect display only.
 * Model/renderer can be linked on a host without this backend. */
int mid_display_start(const mid_display_snapshot *initial);
int mid_display_publish(const mid_display_snapshot *snapshot);
mid_display_hw_state mid_display_hardware_state(void);
#endif
