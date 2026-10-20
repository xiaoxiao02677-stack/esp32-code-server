idf_component_register(
    SRCS
        "src/main.c"
        "src/display.c"
        "src/emopet_face.c"
        "src/overlay.c"
        "src/keys.c"
        "src/audio.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_driver_spi
        esp_driver_gpio
        esp_driver_i2s
        esp_timer
        esp_event
        esp_netif
        esp_wifi
        esp_sntp
        esp_adc
        esp_lcd
        esp_psram
        esp_lvgl_port
        lvgl
)
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu11 -Wno-unused-parameter)
