#include "i2cdev.h"
#include "driver/i2c_master.h"
#include "esp_log.h"

static const char *TAG = "i2cdev";
static i2c_master_bus_handle_t bus_handle = NULL;

static esp_err_t bus_create(int sda_io, int scl_io, i2c_master_bus_handle_t *out)
{
    i2c_master_bus_config_t bus_config = {
        .i2c_port = I2C_NUM_0,
        .sda_io_num = sda_io,
        .scl_io_num = scl_io,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = true,
    };
    return i2c_new_master_bus(&bus_config, out);
}

esp_err_t i2cdev_init(void)
{
    return i2cdev_init_with(I2C_MASTER_SDA_IO, I2C_MASTER_SCL_IO);
}

esp_err_t i2cdev_init_with(int sda_io, int scl_io)
{
    if (bus_handle != NULL) {
        return ESP_OK;
    }
    esp_err_t err = bus_create(sda_io, scl_io, &bus_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "i2c bus on SDA=%d SCL=%d failed: %s",
                 sda_io, scl_io, esp_err_to_name(err));
    }
    return err;
}

esp_err_t i2cdev_deinit(void)
{
    if (bus_handle == NULL) {
        return ESP_OK;
    }
    esp_err_t err = i2c_del_master_bus(bus_handle);
    bus_handle = NULL;
    return err;
}

esp_err_t i2cdev_probe(int sda_io, int scl_io, uint8_t addr)
{
    i2c_master_bus_handle_t bus = NULL;
    esp_err_t err = bus_create(sda_io, scl_io, &bus);
    if (err != ESP_OK) {
        return err;
    }
    err = i2c_master_probe(bus, addr, 50);
    i2c_del_master_bus(bus);
    return err;
}

esp_err_t i2cdev_write(uint8_t addr, const uint8_t *data, size_t len)
{
    if (bus_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    i2c_device_config_t dev_config = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = addr,
        .scl_speed_hz = I2C_MASTER_FREQ_HZ,
    };
    i2c_master_dev_handle_t dev = NULL;
    esp_err_t err = i2c_master_bus_add_device(bus_handle, &dev_config, &dev);
    if (err != ESP_OK) {
        return err;
    }

    err = i2c_master_transmit(dev, data, len, -1);

    i2c_master_bus_rm_device(dev);
    return err;
}
