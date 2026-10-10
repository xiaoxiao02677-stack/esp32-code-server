/*
 * I2C master helper for ESP32-S3 (new driver_i2c API, ESP-IDF v6.x)
 */
#ifndef I2CDEV_H
#define I2CDEV_H

#include "esp_err.h"
#include <stdint.h>

#define I2C_MASTER_SCL_IO  41        /* SCL on GPIO41 */
#define I2C_MASTER_SDA_IO  40        /* SDA on GPIO40 */
#define I2C_MASTER_FREQ_HZ 400000    /* 400 kHz */

/* Install the I2C master bus on the pins above. Safe to call once at boot. */
esp_err_t i2cdev_init(void);

/* Write `len` bytes from `data` to the 7-bit address `addr`.
 * First byte of `data` is typically the register/command byte. */
esp_err_t i2cdev_write(uint8_t addr, const uint8_t *data, uint8_t len);

#endif /* I2CDEV_H */
