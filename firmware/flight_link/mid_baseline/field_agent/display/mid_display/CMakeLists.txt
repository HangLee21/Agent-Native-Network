idf_component_register(SRCS "src/mid_display_model.c" "src/mid_display_render.c" "src/mid_display_idf.c"
    INCLUDE_DIRS "include" PRIV_INCLUDE_DIRS "src"
    REQUIRES esp_driver_gpio esp_driver_i2c esp_timer freertos log)
