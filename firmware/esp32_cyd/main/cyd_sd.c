#include "cyd_sd.h"

#include <stdio.h>

#include "driver/sdspi_host.h"
#include "driver/spi_master.h"
#include "esp_rom_sys.h"
#include "esp_vfs_fat.h"
#include "sdmmc_cmd.h"

#include "board_config.h"

static const char k_mount_point[] = "/C";
static const char k_probe_path[] = "/C/HLV/qemu.txt";

esp_err_t cyd_sd_mount_and_probe(void) {
    spi_bus_config_t bus = {
        .mosi_io_num = BOARD_SD_MOSI,
        .miso_io_num = BOARD_SD_MISO,
        .sclk_io_num = BOARD_SD_SCK,
        .quadwp_io_num = GPIO_NUM_NC,
        .quadhd_io_num = GPIO_NUM_NC,
        .data4_io_num = GPIO_NUM_NC,
        .data5_io_num = GPIO_NUM_NC,
        .data6_io_num = GPIO_NUM_NC,
        .data7_io_num = GPIO_NUM_NC,
        .max_transfer_sz = 4096,
    };
    sdmmc_host_t host = SDSPI_HOST_DEFAULT();
    sdspi_device_config_t device = SDSPI_DEVICE_CONFIG_DEFAULT();
    esp_vfs_fat_sdmmc_mount_config_t mount = {
        .format_if_mount_failed = false,
        .max_files = 8,
        .allocation_unit_size = 16 * 1024,
    };
    sdmmc_card_t *card = NULL;
    char marker[64] = {0};
    FILE *file;
    size_t bytes = 0;
    esp_err_t result;

    result = spi_bus_initialize(SPI3_HOST, &bus, SPI_DMA_CH_AUTO);
    if (result != ESP_OK) {
        esp_rom_printf("D2E_SD_FAIL,bus,%s\n", esp_err_to_name(result));
        return result;
    }

    host.slot = SPI3_HOST;
    host.max_freq_khz = 20000;
    device.host_id = SPI3_HOST;
    device.gpio_cs = BOARD_SD_CS;
    result = esp_vfs_fat_sdspi_mount(k_mount_point, &host, &device, &mount,
                                     &card);
    if (result != ESP_OK) {
        esp_rom_printf("D2E_SD_FAIL,mount,%s\n", esp_err_to_name(result));
        return result;
    }

    file = fopen(k_probe_path, "rb");
    if (file != NULL) {
        bytes = fread(marker, 1, sizeof(marker) - 1U, file);
        fclose(file);
        while (bytes != 0U &&
               (marker[bytes - 1U] == '\r' || marker[bytes - 1U] == '\n')) {
            marker[--bytes] = '\0';
        }
    }
    esp_rom_printf("D2E_SD_READY,sectors=%u,marker=%s\n",
                   (unsigned)card->csd.capacity,
                   bytes != 0U ? marker : "<missing>");
    esp_rom_printf("D2E_DRIVE_READY,drive=C,type=sd-fat,sectors=%u\n",
                   (unsigned)card->csd.capacity);
    return ESP_OK;
}
