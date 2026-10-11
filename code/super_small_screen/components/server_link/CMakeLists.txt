idf_component_register(SRCS "server_link.c"
                       INCLUDE_DIRS "include"
                       # 托管组件用全限定名（namespace__name），与参考工程写法一致
                       REQUIRES espressif__esp_websocket_client esp_event nvs_flash
                       PRIV_REQUIRES espressif__cjson)
