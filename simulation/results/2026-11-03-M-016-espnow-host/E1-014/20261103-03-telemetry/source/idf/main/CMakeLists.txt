idf_component_register(SRCS "app_main.c" "../../src/ann.c" "../../src/ann_console.c" "../../src/ann_log.c"
 INCLUDE_DIRS "../../include" "../../src" REQUIRES esp_wifi esp_event esp_netif esp_timer nvs_flash esp_hw_support json)
