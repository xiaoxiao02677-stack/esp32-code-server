#!/bin/bash
# Cross syntax-check for main/main.c (integration of all local components)
# See tools/wifi_check.sh for the single-file variant.
set -e
XT="/d/INSTALL/esp/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
IDF="D:/INSTALL/esp/v6.1/esp-idf"
PICO="/d/INSTALL/esp/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/picolibc"
ROOT="$(cygpath -m "$0" | xargs dirname)/.."

CFG="$(mktemp -d)"
grep -E '^CONFIG_(LWIP|ESP_NETIF|TCP|IP_|ESP_WIFI|FREERTOS|SOC_|IDF_TARGET|LOG|ESP_SYSTEM|ESP_INT)' \
  "G:/demo/21_xiaozhi/code/small_secreen/xiaozhi-esp32/sdkconfig" \
  | grep -vE '=n$|=""|not set' \
  | sed 's/=y$/ 1/; s/="\([^"]*\)"/ "\1"/; s/=\([0-9][0-9xXa-fA-F]*\)$/ \1/' \
  | sed 's/^/#define /' > "$CFG/sdkconfig.h"
echo '#define CONFIG_IDF_TARGET_ESP32S3 1' >> "$CFG/sdkconfig.h"

"$XT" -fsyntax-only -std=gnu17 -Wall -Wextra \
  -I"$CFG" \
  -isystem "$PICO/include" \
  -isystem "$PICO/xtensa-esp-elf/include" \
  -isystem "$PICO/xtensa-esp-elf/sys-include" \
  $(for d in \
    "$IDF/components/freertos/FreeRTOS-Kernel/include" \
    "$IDF/components/freertos/FreeRTOS-Kernel/portable/xtensa/include/freertos" \
    "$IDF/components/freertos/config/include" \
    "$IDF/components/freertos/config/include/freertos" \
    "$IDF/components/freertos/config/xtensa/include" \
    "$IDF/components/xtensa/include" \
    "$IDF/components/xtensa/esp32s3/include" \
    "$IDF/components/esp_libc/platform_include" \
    "$IDF/components/esp_libc/include" \
    "$IDF/components/esp_wifi/include" \
    "$IDF/components/esp_wifi/include/esp32s3" \
    "$IDF/components/esp_common/include" \
    "$IDF/components/esp_common/include/esp32s3" \
    "$IDF/components/esp_hw_support/include" \
    "$IDF/components/esp_hw_support/include/esp32s3" \
    "$IDF/components/esp_hw_support/port/esp32s3/private_include" \
    "$IDF/components/esp_system/include" \
    "$IDF/components/esp_system/port/esp32s3/include" \
    "$IDF/components/esp_netif/include" \
    "$IDF/components/esp_netif_stack/include" \
    "$IDF/components/esp_event/include" \
    "$IDF/components/esp_event/include/esp32s3" \
    "$IDF/components/esp_timer/include" \
    "$IDF/components/log/include" \
    "$IDF/components/soc/include" \
    "$IDF/components/soc/include/esp32s3" \
    "$IDF/components/soc/esp32s3/include" \
    "$IDF/components/soc/esp32s3/register" \
    "$IDF/components/hal/include" \
    "$IDF/components/hal/esp32s3/include" \
    "$IDF/components/nvs_flash/include" \
    "$IDF/components/lwip/include" \
    "$IDF/components/lwip/port/include" \
    "$IDF/components/lwip/port/freertos/include" \
    "$IDF/components/lwip/port/esp32xx/include" \
    "$IDF/components/lwip/lwip/src/include" \
    "$IDF/components/esp_rom/include" \
    "$IDF/components/esp_rom/include/esp32s3" \
    "$IDF/components/esp_rom/esp32s3/include" \
    "$IDF/components/esp_partition/include" \
    "$IDF/components/esp_blockdev/include" \
    "$IDF/components/heap/include" \
    "$IDF/components/esp_mm/include" \
    "$IDF/components/esp_pm/include" \
    "$IDF/components/esp_driver_i2c/include" \
    "$ROOT/components/ssd1306/include" \
    "$ROOT/components/wifi_manager/include" \
    "$ROOT/components/server_link/include" \
    "$ROOT/main" \
    ; do printf -- "-I%s " "$d"; done) "$ROOT/main/main.c"

echo "OK: main.c syntax clean"
