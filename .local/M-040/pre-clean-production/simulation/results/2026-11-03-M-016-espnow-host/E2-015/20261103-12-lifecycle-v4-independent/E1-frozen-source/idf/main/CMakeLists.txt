idf_component_register(SRCS "app_main.c" "../../src/ann.c" "../../src/ann_console.c" "../../src/ann_log.c"
 INCLUDE_DIRS "../../include" "../../src" REQUIRES esp_wifi esp_event esp_netif esp_timer nvs_flash esp_hw_support json)
set(ANN_SOURCE_IDENTITIES "")
foreach(ANN_SOURCE app_main.c ../../src/ann.c ../../src/ann_console.c ../../src/ann_log.c ../../include/ann.h ../../include/ann_console.h)
 file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/${ANN_SOURCE}" ANN_FILE_HASH)
 string(APPEND ANN_SOURCE_IDENTITIES "${ANN_FILE_HASH}")
endforeach()
string(SHA256 ANN_BUILD_HASH "${ANN_SOURCE_IDENTITIES}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE ANN_BUILD_ID="ann-v1-${ANN_BUILD_HASH}")
