#include "cyd_flash.h"

#include <stddef.h>

#include "esp_littlefs.h"
#include "esp_rom_sys.h"

static const char k_mount_point[] = "/A";
static const char k_partition_label[] = "storage";

esp_err_t cyd_flash_mount(void) {
    const esp_vfs_littlefs_conf_t mount = {
        .base_path = k_mount_point,
        .partition_label = k_partition_label,
        .format_if_mount_failed = true,
        .read_only = false,
        .dont_mount = false,
        .grow_on_mount = true,
    };
    size_t total_bytes = 0U;
    size_t used_bytes = 0U;
    esp_err_t result = esp_vfs_littlefs_register(&mount);

    if (result != ESP_OK) {
        esp_rom_printf("D2E_DRIVE_FAIL,drive=A,type=littlefs,error=%s\n",
                       esp_err_to_name(result));
        return result;
    }
    result = esp_littlefs_info(k_partition_label, &total_bytes, &used_bytes);
    if (result != ESP_OK) {
        esp_rom_printf("D2E_DRIVE_FAIL,drive=A,type=littlefs,error=%s\n",
                       esp_err_to_name(result));
        return result;
    }
    esp_rom_printf("D2E_DRIVE_READY,drive=A,type=littlefs,total=%u,used=%u\n",
                   (unsigned)total_bytes, (unsigned)used_bytes);
    return ESP_OK;
}
