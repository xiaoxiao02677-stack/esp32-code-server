# ESP32-S3 + 0.42" OLED (SSD1306 72x40) HelloWorld
cmake_minimum_required(VERSION 3.16)
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/components")

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(super_small_screen)
