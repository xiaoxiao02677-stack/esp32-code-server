idf_component_register(SRCS "main.c" "ui_status.c" "wifi_bridge.cc"
                       INCLUDE_DIRS "."
                       REQUIRES ssd1306 wifi_connect server_link
                       PRIV_REQUIRES nvs_flash)
