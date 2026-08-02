#include "cyd_flash.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "d2e/xip_imports.h"
#include "esp_partition.h"
#include "esp_rom_crc.h"
#include "esp_rom_sys.h"
#include "mbedtls/sha256.h"

enum {
    k_catalog_size = 0x10000,
    k_superblock_size = 256,
    k_record_size = 64,
    k_copy_buffer_size = 1024,
    k_flash_sector_size = 4096,
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
static d2e_native_program active_program;
static d2e_native_image_fragment *active_fragments;
static d2e_mz_relocation *active_mz_relocations;
static esp_partition_mmap_handle_t active_irom_handle;
static esp_partition_mmap_handle_t active_drom_handle;

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

static int digest_valid(const d2e_xip_module_view *view) {
    static const uint8_t zero_digest[D2E_XIP_HASH_SIZE];
    uint8_t digest[D2E_XIP_HASH_SIZE];
    mbedtls_sha256_context context;
    int result;
    mbedtls_sha256_init(&context);
    result = mbedtls_sha256_starts(&context, 0);
    if (result == 0) {
        result = mbedtls_sha256_update(&context, view->bytes, 205U);
    }
    if (result == 0) {
        result = mbedtls_sha256_update(&context, zero_digest,
                                       sizeof(zero_digest));
    }
    if (result == 0) {
        result = mbedtls_sha256_update(
            &context, view->bytes + 237U,
            view->manifest.module_size - 237U);
    }
    if (result == 0) {
        result = mbedtls_sha256_finish(&context, digest);
    }
    mbedtls_sha256_free(&context);
    return result == 0 &&
           memcmp(digest, view->manifest.sha256, sizeof(digest)) == 0;
}

static esp_err_t read_manifest(uint32_t offset, uint32_t size,
                               d2e_xip_manifest *manifest,
                               int verify_digest) {
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
    } else if (verify_digest && !digest_valid(&view)) {
        result = ESP_ERR_INVALID_CRC;
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

static esp_err_t append_catalog_record(const cyd_flash_module *module) {
    uint8_t record[k_record_size];
    esp_err_t result;
    if (state.next_record_offset + k_record_size > k_catalog_size) {
        return ESP_ERR_NO_MEM;
    }
    memset(record, 0xff, sizeof(record));
    memcpy(record, k_record_magic, sizeof(k_record_magic));
    write_u32(record + 8U, module->partition_offset);
    write_u32(record + 12U, module->module_size);
    write_u32(record + 16U, module->expected_irom_address);
    write_u32(record + 20U, module->expected_drom_address);
    memcpy(record + 24U, module->manifest.sha256, D2E_XIP_HASH_SIZE);
    write_u32(record + 56U, module->import_fingerprint);
    write_u32(record + 60U,
              esp_rom_crc32_le(0U, record, k_record_size - 4U));
    result = esp_partition_write(state.partition, state.next_record_offset,
                                 record, sizeof(record));
    if (result == ESP_OK) {
        state.next_record_offset += k_record_size;
    }
    return result;
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
        module.import_fingerprint = read_u32(record + 56U);
        if (module.partition_offset < k_catalog_size ||
            module.partition_offset % D2E_XIP_FLASH_PAGE_SIZE != 0U ||
            module.partition_offset > state.partition->size ||
            module.module_size > state.partition->size -
                                     module.partition_offset ||
            read_manifest(module.partition_offset, module.module_size,
                          &module.manifest, 0) != ESP_OK ||
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

static void report_xip_window(void) {
    const void *irom = NULL;
    const void *drom = NULL;
    esp_partition_mmap_handle_t irom_handle = 0;
    esp_partition_mmap_handle_t drom_handle = 0;
    const esp_err_t irom_result = esp_partition_mmap(
        state.partition, k_catalog_size, D2E_XIP_FLASH_PAGE_SIZE,
        ESP_PARTITION_MMAP_INST, &irom, &irom_handle);
    const esp_err_t drom_result = esp_partition_mmap(
        state.partition, k_catalog_size, D2E_XIP_FLASH_PAGE_SIZE,
        ESP_PARTITION_MMAP_DATA, &drom, &drom_handle);
    if (irom_result == ESP_OK && drom_result == ESP_OK) {
        esp_rom_printf("D2E_XIP_WINDOW,irom=%p,drom=%p\n", irom, drom);
    }
    if (drom_result == ESP_OK) {
        esp_partition_munmap(drom_handle);
    }
    if (irom_result == ESP_OK) {
        esp_partition_munmap(irom_handle);
    }
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
        report_xip_window();
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
                           &module.manifest, 1);
    if (result != ESP_OK) {
        return result;
    }
    module.expected_irom_address = 0U;
    module.expected_drom_address = UINT32_C(0x10000000);
    module.import_fingerprint = 0U;
    result = append_catalog_record(&module);
    if (result != ESP_OK) {
        return result;
    }
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

static esp_err_t map_module(const cyd_flash_module *module, const void **irom,
                            const void **drom,
                            esp_partition_mmap_handle_t *irom_handle,
                            esp_partition_mmap_handle_t *drom_handle) {
    esp_err_t result = esp_partition_mmap(
        state.partition,
        module->partition_offset + module->manifest.irom_offset,
        module->manifest.irom_size, ESP_PARTITION_MMAP_INST, irom,
        irom_handle);
    if (result != ESP_OK) {
        return result;
    }
    result = esp_partition_mmap(
        state.partition,
        module->partition_offset + module->manifest.drom_offset,
        module->manifest.drom_size, ESP_PARTITION_MMAP_DATA, drom,
        drom_handle);
    if (result != ESP_OK) {
        esp_partition_munmap(*irom_handle);
    }
    return result;
}

static esp_err_t flush_patch_sector(uint32_t sector_offset,
                                    const uint8_t *sector_bytes) {
    esp_err_t result = esp_partition_erase_range(
        state.partition, sector_offset, k_flash_sector_size);
    if (result == ESP_OK) {
        result = esp_partition_write(state.partition, sector_offset,
                                     sector_bytes, k_flash_sector_size);
    }
    return result;
}

static esp_err_t relocate_module(cyd_flash_module *module,
                                 uint32_t irom_address,
                                 uint32_t drom_address) {
    uint8_t record[D2E_XIP_RELOCATION_SIZE];
    uint32_t current_sector = UINT32_MAX;
    uint32_t index;
    esp_err_t result = ESP_OK;
    uint8_t *const sector_bytes = malloc(k_flash_sector_size);
    if (sector_bytes == NULL) {
        return ESP_ERR_NO_MEM;
    }
    for (index = 0U; index < module->manifest.relocation_count; ++index) {
        uint32_t patch_offset;
        uint32_t target_kind;
        uint32_t target;
        int32_t addend;
        uintptr_t value;
        uint32_t absolute_patch;
        uint32_t sector;
        result = esp_partition_read(
            state.partition,
            module->partition_offset + module->manifest.relocation_offset +
                index * D2E_XIP_RELOCATION_SIZE,
            record, sizeof(record));
        if (result != ESP_OK) {
            break;
        }
        patch_offset = read_u32(record);
        target_kind = read_u32(record + 4U);
        target = read_u32(record + 8U);
        addend = (int32_t)read_u32(record + 12U);
        if (target_kind == D2E_XIP_TARGET_IROM) {
            value = (uintptr_t)irom_address + target;
        } else if (target_kind == D2E_XIP_TARGET_DROM) {
            value = (uintptr_t)drom_address + target;
        } else if (target_kind == D2E_XIP_TARGET_IMPORT &&
                   d2e_xip_import_resolve(target, &value)) {
            /* Resolved through the resident shell ABI. */
        } else {
            result = ESP_ERR_NOT_SUPPORTED;
            break;
        }
        value = (uintptr_t)((intptr_t)value + addend);
        if (value > UINT32_MAX) {
            result = ESP_ERR_INVALID_SIZE;
            break;
        }
        absolute_patch = module->partition_offset + patch_offset;
        sector = absolute_patch - absolute_patch % k_flash_sector_size;
        if (sector != current_sector) {
            if (current_sector != UINT32_MAX) {
                result = flush_patch_sector(current_sector, sector_bytes);
                if (result != ESP_OK) {
                    break;
                }
            }
            result = esp_partition_read(state.partition, sector, sector_bytes,
                                        k_flash_sector_size);
            if (result != ESP_OK) {
                break;
            }
            current_sector = sector;
        }
        write_u32(sector_bytes + absolute_patch - sector, (uint32_t)value);
    }
    if (result == ESP_OK && current_sector != UINT32_MAX) {
        result = flush_patch_sector(current_sector, sector_bytes);
    }
    if (result == ESP_OK) {
        module->expected_irom_address = irom_address;
        module->expected_drom_address = drom_address;
        module->import_fingerprint = d2e_xip_import_fingerprint();
        result = append_catalog_record(module);
    }
    free(sector_bytes);
    return result;
}

static esp_err_t build_active_program(const cyd_flash_module *module,
                                      const void *irom, const void *drom) {
    uint32_t index;
    uint8_t record[D2E_XIP_FRAGMENT_SIZE];
    if (module->manifest.fragment_count > SIZE_MAX / sizeof(*active_fragments) ||
        module->manifest.mz_relocation_count >
            SIZE_MAX / sizeof(*active_mz_relocations)) {
        return ESP_ERR_INVALID_SIZE;
    }
    if (module->manifest.fragment_count != 0U) {
        active_fragments = calloc(module->manifest.fragment_count,
                                  sizeof(*active_fragments));
        if (active_fragments == NULL) {
            return ESP_ERR_NO_MEM;
        }
    }
    if (module->manifest.mz_relocation_count != 0U) {
        active_mz_relocations = calloc(module->manifest.mz_relocation_count,
                                       sizeof(*active_mz_relocations));
        if (active_mz_relocations == NULL) {
            free(active_fragments);
            active_fragments = NULL;
            return ESP_ERR_NO_MEM;
        }
    }
    for (index = 0U; index < module->manifest.fragment_count; ++index) {
        const uint32_t table_offset =
            module->partition_offset + module->manifest.fragment_offset +
            index * D2E_XIP_FRAGMENT_SIZE;
        esp_err_t result = esp_partition_read(state.partition, table_offset,
                                              record, sizeof(record));
        uint32_t data_offset;
        if (result != ESP_OK) {
            return result;
        }
        data_offset = read_u32(record + 4U);
        active_fragments[index].offset = read_u32(record);
        active_fragments[index].data =
            (const uint8_t *)drom + data_offset - module->manifest.drom_offset;
        active_fragments[index].size = read_u32(record + 8U);
    }
    for (index = 0U; index < module->manifest.mz_relocation_count; ++index) {
        uint8_t mz_record[D2E_XIP_MZ_RELOCATION_SIZE];
        const uint32_t table_offset =
            module->partition_offset + module->manifest.mz_relocation_offset +
            index * D2E_XIP_MZ_RELOCATION_SIZE;
        esp_err_t result = esp_partition_read(state.partition, table_offset,
                                              mz_record, sizeof(mz_record));
        if (result != ESP_OK) {
            return result;
        }
        active_mz_relocations[index].offset =
            (uint16_t)(mz_record[0] | ((uint16_t)mz_record[1] << 8U));
        active_mz_relocations[index].segment =
            (uint16_t)(mz_record[2] | ((uint16_t)mz_record[3] << 8U));
    }
    memset(&active_program, 0, sizeof(active_program));
    active_program.name = module->manifest.name;
    active_program.format = module->manifest.image_format;
    active_program.load_segment = module->manifest.load_segment;
    active_program.entry_cs = module->manifest.entry_cs;
    active_program.entry_ip = module->manifest.entry_ip;
    active_program.initial_ss = module->manifest.initial_ss;
    active_program.initial_sp = module->manifest.initial_sp;
    active_program.image_size = module->manifest.image_size;
    active_program.relocations = active_mz_relocations;
    active_program.relocation_count = module->manifest.mz_relocation_count;
    active_program.region = (d2e_native_region_fn)(
        (const uint8_t *)irom + module->manifest.region_offset);
    active_program.image_fragments = active_fragments;
    active_program.image_fragment_count = module->manifest.fragment_count;
    return ESP_OK;
}

esp_err_t cyd_flash_activate_module(size_t index, d2e_package *package) {
    cyd_flash_module *module;
    const void *irom = NULL;
    const void *drom = NULL;
    uint32_t irom_address;
    uint32_t drom_address;
    esp_err_t result;
    if (index >= state.module_count || package == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    cyd_flash_deactivate_module();
    module = &state.modules[index];
    result = map_module(module, &irom, &drom, &active_irom_handle,
                        &active_drom_handle);
    if (result != ESP_OK) {
        return result;
    }
    irom_address = (uint32_t)(uintptr_t)irom;
    drom_address = (uint32_t)(uintptr_t)drom;
    esp_partition_munmap(active_drom_handle);
    esp_partition_munmap(active_irom_handle);
    active_drom_handle = 0;
    active_irom_handle = 0;
    if (module->expected_irom_address != irom_address ||
        module->expected_drom_address != drom_address ||
        module->import_fingerprint != d2e_xip_import_fingerprint()) {
        result = relocate_module(module, irom_address, drom_address);
        if (result != ESP_OK) {
            return result;
        }
    }
    result = map_module(module, &irom, &drom, &active_irom_handle,
                        &active_drom_handle);
    if (result != ESP_OK) {
        return result;
    }
    if ((uint32_t)(uintptr_t)irom != irom_address ||
        (uint32_t)(uintptr_t)drom != drom_address) {
        cyd_flash_deactivate_module();
        return ESP_ERR_INVALID_STATE;
    }
    result = build_active_program(module, irom, drom);
    if (result != ESP_OK) {
        cyd_flash_deactivate_module();
        return result;
    }
    package->abi_version = D2E_PACKAGE_ABI_VERSION;
    package->command = module->manifest.command;
    package->title = module->manifest.title;
    package->storage = D2E_PACKAGE_EXTERNAL_MODULE;
    package->program = &active_program;
    esp_rom_printf("D2E_MODULE_ACTIVE,command=%s,irom=%p,drom=%p\n",
                   module->manifest.command, irom, drom);
    return ESP_OK;
}

void cyd_flash_deactivate_module(void) {
    free(active_mz_relocations);
    free(active_fragments);
    active_mz_relocations = NULL;
    active_fragments = NULL;
    memset(&active_program, 0, sizeof(active_program));
    if (active_drom_handle != 0) {
        esp_partition_munmap(active_drom_handle);
        active_drom_handle = 0;
    }
    if (active_irom_handle != 0) {
        esp_partition_munmap(active_irom_handle);
        active_irom_handle = 0;
    }
}
