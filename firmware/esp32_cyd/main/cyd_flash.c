#include "cyd_flash.h"

#include <stdio.h>
#include <string.h>

#include "esp_partition.h"
#include "esp_rom_crc.h"
#include "esp_rom_sys.h"

enum {
    k_catalog_size = 0x10000,
    k_superblock_size = 256,
    k_record_size = 64,
    k_copy_buffer_size = 1024,
};

static const char k_partition_label[] = "storage";
static const uint8_t k_superblock_magic[8] = {'D', '2', 'E', 'A', 'X', 'I',
                                              'P', '1'};
static const uint8_t k_record_magic[8] = {'D', '2', 'E', 'M', 'O', 'D', '1', 0};

typedef struct cyd_flash_state {
    const esp_partition_t *partition;
    cyd_flash_module modules[CYD_FLASH_MODULE_CAPACITY];
    size_t module_count;
    uint32_t next_module_offset;
    uint32_t next_record_offset;
} cyd_flash_state;

static cyd_flash_state state;

static uint32_t read_u32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8U) |
           ((uint32_t)bytes[2] << 16U) | ((uint32_t)bytes[3] << 24U);
}

static void write_u32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8U);
    bytes[2] = (uint8_t)(value >> 16U);
    bytes[3] = (uint8_t)(value >> 24U);
}

static uint32_t align_up(uint32_t value, uint32_t alignment) {
    return value + (alignment - value % alignment) % alignment;
}

static int command_equal(const char *left, const char *right) {
    while (*left != 0 && *right != 0) {
        char a = *left++;
        char b = *right++;
        if (a >= 'a' && a <= 'z') {
            a = (char)(a - 'a' + 'A');
        }
        if (b >= 'a' && b <= 'z') {
            b = (char)(b - 'a' + 'A');
        }
        if (a != b) {
            return 0;
        }
    }
    return *left == 0 && *right == 0;
}

static esp_err_t format_store(void) {
    uint8_t superblock[k_superblock_size];
    esp_err_t result = esp_partition_erase_range(state.partition, 0,
                                                  state.partition->size);
    if (result != ESP_OK) {
        return result;
    }
    memset(superblock, 0xff, sizeof(superblock));
    memcpy(superblock, k_superblock_magic, sizeof(k_superblock_magic));
    write_u32(superblock + 8U, 1U);
    write_u32(superblock + 12U, k_catalog_size);
    write_u32(superblock + 16U, k_record_size);
    write_u32(superblock + 252U,
              esp_rom_crc32_le(0U, superblock, sizeof(superblock) - 4U));
    result = esp_partition_write(state.partition, 0, superblock,
                                 sizeof(superblock));
    if (result == ESP_OK) {
        esp_rom_printf("D2E_DRIVE_FORMAT,drive=A,type=xip\n");
    }
    return result;
}

static int valid_superblock(const uint8_t *superblock) {
    return memcmp(superblock, k_superblock_magic,
                  sizeof(k_superblock_magic)) == 0 &&
           read_u32(superblock + 8U) == 1U &&
           read_u32(superblock + 12U) == k_catalog_size &&
           read_u32(superblock + 16U) == k_record_size &&
           read_u32(superblock + 252U) ==
               esp_rom_crc32_le(0U, superblock, k_superblock_size - 4U);
}

static esp_err_t read_manifest(uint32_t offset, uint32_t size,
                               d2e_xip_manifest *manifest) {
    const void *mapped = NULL;
    esp_partition_mmap_handle_t handle = 0;
    d2e_xip_module_view view;
    esp_err_t result = esp_partition_mmap(state.partition, offset, size,
                                          ESP_PARTITION_MMAP_DATA, &mapped,
                                          &handle);
    if (result != ESP_OK) {
        return result;
    }
    if (!d2e_xip_module_open(&view, mapped, size)) {
        result = ESP_ERR_INVALID_RESPONSE;
    } else {
        *manifest = view.manifest;
    }
    esp_partition_munmap(handle);
    return result;
}

static void add_module(const cyd_flash_module *module) {
    size_t index;
    for (index = 0U; index < state.module_count; ++index) {
        if (command_equal(state.modules[index].manifest.command,
                          module->manifest.command)) {
            state.modules[index] = *module;
            return;
        }
    }
    if (state.module_count < CYD_FLASH_MODULE_CAPACITY) {
        state.modules[state.module_count++] = *module;
    }
}

static esp_err_t scan_catalog(void) {
    uint8_t record[k_record_size];
    uint32_t offset;
    state.module_count = 0U;
    state.next_module_offset = k_catalog_size;
    state.next_record_offset = k_superblock_size;
    for (offset = k_superblock_size; offset + k_record_size <= k_catalog_size;
         offset += k_record_size) {
        cyd_flash_module module;
        esp_err_t result = esp_partition_read(state.partition, offset, record,
                                              sizeof(record));
        if (result != ESP_OK) {
            return result;
        }
        if (record[0] == UINT8_C(0xff)) {
            state.next_record_offset = offset;
            return ESP_OK;
        }
        if (memcmp(record, k_record_magic, sizeof(k_record_magic)) != 0 ||
            read_u32(record + 60U) !=
                esp_rom_crc32_le(0U, record, k_record_size - 4U)) {
            esp_rom_printf("D2E_MODULE_SKIP,reason=catalog,offset=%u\n",
                           (unsigned)offset);
            continue;
        }
        memset(&module, 0, sizeof(module));
        module.partition_offset = read_u32(record + 8U);
        module.module_size = read_u32(record + 12U);
        module.expected_irom_address = read_u32(record + 16U);
        module.expected_drom_address = read_u32(record + 20U);
        if (module.partition_offset < k_catalog_size ||
            module.partition_offset % D2E_XIP_FLASH_PAGE_SIZE != 0U ||
            module.partition_offset > state.partition->size ||
            module.module_size > state.partition->size -
                                     module.partition_offset ||
            read_manifest(module.partition_offset, module.module_size,
                          &module.manifest) != ESP_OK ||
            memcmp(record + 24U, module.manifest.sha256,
                   D2E_XIP_HASH_SIZE) != 0) {
            esp_rom_printf("D2E_MODULE_SKIP,reason=module,offset=%u\n",
                           (unsigned)module.partition_offset);
            continue;
        }
        add_module(&module);
        {
            const uint32_t end = align_up(module.partition_offset +
                                              module.module_size,
                                          D2E_XIP_FLASH_PAGE_SIZE);
            if (end > state.next_module_offset) {
                state.next_module_offset = end;
            }
        }
    }
    state.next_record_offset = k_catalog_size;
    return ESP_OK;
}

esp_err_t cyd_flash_mount(void) {
    uint8_t superblock[k_superblock_size];
    esp_err_t result;
    memset(&state, 0, sizeof(state));
    state.partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_ANY, k_partition_label);
    if (state.partition == NULL ||
        state.partition->address % D2E_XIP_FLASH_PAGE_SIZE != 0U ||
        state.partition->size < 2U * D2E_XIP_FLASH_PAGE_SIZE) {
        return ESP_ERR_NOT_FOUND;
    }
    result = esp_partition_read(state.partition, 0, superblock,
                                sizeof(superblock));
    if (result != ESP_OK) {
        return result;
    }
    if (!valid_superblock(superblock)) {
        result = format_store();
        if (result != ESP_OK) {
            return result;
        }
    }
    result = scan_catalog();
    if (result == ESP_OK) {
        esp_rom_printf("D2E_DRIVE_READY,drive=A,type=xip,total=%u,used=%u,"
                       "modules=%u\n",
                       (unsigned)state.partition->size,
                       (unsigned)state.next_module_offset,
                       (unsigned)state.module_count);
    }
    return result;
}

static int valid_source_path(const char *path) {
    return path != NULL && *path != 0 && strstr(path, "..") == NULL &&
           path[0] != '/' && path[0] != '\\';
}

esp_err_t cyd_flash_install_file(const char *path) {
    char full_path[96];
    FILE *file;
    long file_size;
    uint32_t erase_size;
    uint32_t written = 0U;
    uint8_t buffer[k_copy_buffer_size];
    cyd_flash_module module;
    uint8_t record[k_record_size];
    esp_err_t result = ESP_OK;
    if (state.partition == NULL || !valid_source_path(path)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (snprintf(full_path, sizeof(full_path), "/C/%s", path) >=
        (int)sizeof(full_path)) {
        return ESP_ERR_INVALID_SIZE;
    }
    file = fopen(full_path, "rb");
    if (file == NULL) {
        return ESP_ERR_NOT_FOUND;
    }
    if (fseek(file, 0, SEEK_END) != 0 || (file_size = ftell(file)) <= 0 ||
        (unsigned long)file_size > UINT32_MAX || fseek(file, 0, SEEK_SET) != 0) {
        fclose(file);
        return ESP_ERR_INVALID_SIZE;
    }
    erase_size = align_up((uint32_t)file_size, UINT32_C(0x1000));
    if (state.next_record_offset + k_record_size > k_catalog_size ||
        state.next_module_offset > state.partition->size ||
        erase_size > state.partition->size - state.next_module_offset) {
        fclose(file);
        return ESP_ERR_NO_MEM;
    }
    result = esp_partition_erase_range(state.partition,
                                       state.next_module_offset, erase_size);
    while (result == ESP_OK && written < (uint32_t)file_size) {
        const size_t count = fread(buffer, 1U, sizeof(buffer), file);
        if (count == 0U) {
            result = ESP_ERR_INVALID_RESPONSE;
            break;
        }
        result = esp_partition_write(state.partition,
                                     state.next_module_offset + written,
                                     buffer, count);
        written += (uint32_t)count;
    }
    fclose(file);
    if (result != ESP_OK || written != (uint32_t)file_size) {
        return result != ESP_OK ? result : ESP_ERR_INVALID_SIZE;
    }
    memset(&module, 0, sizeof(module));
    module.partition_offset = state.next_module_offset;
    module.module_size = (uint32_t)file_size;
    result = read_manifest(module.partition_offset, module.module_size,
                           &module.manifest);
    if (result != ESP_OK) {
        return result;
    }
    memset(record, 0xff, sizeof(record));
    memcpy(record, k_record_magic, sizeof(k_record_magic));
    write_u32(record + 8U, module.partition_offset);
    write_u32(record + 12U, module.module_size);
    memcpy(record + 24U, module.manifest.sha256, D2E_XIP_HASH_SIZE);
    write_u32(record + 60U,
              esp_rom_crc32_le(0U, record, k_record_size - 4U));
    result = esp_partition_write(state.partition, state.next_record_offset,
                                 record, sizeof(record));
    if (result != ESP_OK) {
        return result;
    }
    state.next_record_offset += k_record_size;
    state.next_module_offset = align_up(module.partition_offset +
                                            module.module_size,
                                        D2E_XIP_FLASH_PAGE_SIZE);
    add_module(&module);
    esp_rom_printf("D2E_MODULE_INSTALLED,command=%s,bytes=%u,offset=%u\n",
                   module.manifest.command, (unsigned)module.module_size,
                   (unsigned)module.partition_offset);
    return ESP_OK;
}

size_t cyd_flash_module_count(void) { return state.module_count; }

const cyd_flash_module *cyd_flash_module_at(size_t index) {
    return index < state.module_count ? &state.modules[index] : NULL;
}
