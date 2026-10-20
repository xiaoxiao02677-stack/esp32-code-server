idf_component_register(
    SRCS
        "src/main.c"
        "src/display.c"
        "src/pet_canvas.c"
        "src/boot_anim.c"
        "src/ui_screens.c"
        "src/keys.c"
        "src/audio.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_driver_spi
        esp_driver_gpio
        esp_driver_i2s
        esp_timer
        esp_lcd
        esp_psram
        esp_lvgl_port
        lvgl
)

# v6.x 默认 gnu23 且警告即错误：本项目按 gnu11 编写更稳，显式锁定
target_compile_options(${COMPONENT_LIB} PRIVATE -std=gnu11 -Wno-unused-parameter)
