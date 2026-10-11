idf_component_register(SRCS "main.c" "ui_status.c"
                       INCLUDE_DIRS "."
                       REQUIRES ssd1306 wifi_manager server_link
                       PRIV_REQUIRES nvs_flash)
