#ifndef D2E_CYD_FLASH_H
#define D2E_CYD_FLASH_H

#include <stddef.h>
#include <stdint.h>

#include "d2e/xip_module.h"
#include "esp_err.h"

enum {
    CYD_FLASH_MODULE_CAPACITY = 8,
    CYD_FLASH_AUTOEXEC_CAPACITY = 48,
};

typedef struct cyd_flash_module {
    uint32_t partition_offset;
    uint32_t module_size;
    uint32_t expected_irom_address;
    uint32_t expected_drom_address;
    uint32_t import_fingerprint;
    d2e_xip_manifest manifest;
} cyd_flash_module;

esp_err_t cyd_flash_mount(void);
esp_err_t cyd_flash_install_file(const char *path);
esp_err_t cyd_flash_read_autoexec(char *buffer, size_t capacity,
                                  size_t *length);
size_t cyd_flash_module_count(void);
const cyd_flash_module *cyd_flash_module_at(size_t index);
esp_err_t cyd_flash_activate_module(size_t index, d2e_package *package);
void cyd_flash_deactivate_module(void);

#endif
