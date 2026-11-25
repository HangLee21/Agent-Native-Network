#include "mid_display.h"
/* No display task, GPIO, power switch, I2C driver, renderer or timers. */
int mid_display_start(const mid_display_snapshot *initial) { (void)initial; return 0; }
int mid_display_publish(const mid_display_snapshot *snapshot) { (void)snapshot; return 0; }
mid_display_hw_state mid_display_hardware_state(void) { return MID_DISPLAY_HW_OFF; }
