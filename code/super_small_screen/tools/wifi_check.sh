#!/bin/bash
# Cross syntax-check for components/wifi_manager/wifi_manager.c
# Uses xtensa-esp32s3-elf-gcc + local IDF v6.1 headers + generated sdkconfig stub.
# Host-only check: no linking, no flashing. Rerun after editing wifi_manager.c:
#   bash G:/demo/21_xiaozhi/code/super_small_screen/tools/wifi_check.sh
set -e
XT="/d/INSTALL/esp/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/bin/xtensa-esp32s3-elf-gcc.exe"
IDF="D:/INSTALL/esp/v6.1/esp-idf"
PICO="/d/INSTALL/esp/tools/xtensa-esp-elf/esp-15.2.0_20251204/xtensa-esp-elf/picolibc"
W="$(cygpath -m "$0" | xargs dirname)/../components/wifi_manager"
SRC="$W/wifi_manager.c"

# sdkconfig stub generated once from the reference project's real sdkconfig
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
    "$W/include" \
    ; do printf -- "-I%s " "$d"; done) "$SRC"

echo "OK: wifi_manager.c syntax clean"
