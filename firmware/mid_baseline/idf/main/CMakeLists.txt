idf_component_register(SRCS "app_main.c" "../../mid.c" INCLUDE_DIRS "../.."
 REQUIRES esp_wifi esp_event esp_netif esp_timer nvs_flash esp_hw_support json mid_display)
set(IDENTITIES "")
foreach(F app_main.c CMakeLists.txt ../../mid.c ../../mid.h ../CMakeLists.txt ../sdkconfig.defaults ../../../mid_display/CMakeLists.txt ../../../mid_display/include/mid_display.h ../../../mid_display/src/mid_display_model.c ../../../mid_display/src/mid_display_render.c ../../../mid_display/src/mid_display_idf.c ../../../mid_display/src/mid_display_font.h)
 file(SHA256 "${CMAKE_CURRENT_LIST_DIR}/${F}" H)
 string(APPEND IDENTITIES "${H}")
endforeach()
string(SHA256 BUILD_HASH "${IDENTITIES}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE MID_BUILD_ID="mid-v1-${BUILD_HASH}")
