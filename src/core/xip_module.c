#include "d2e/xip_module.h"

#include <ctype.h>
#include <string.h>

static const uint8_t module_magic[8] = {'D', '2', 'E', 'X', 'I', 'P', '1', 0};

static uint16_t read_u16(const uint8_t *bytes) {
    return (uint16_t)(bytes[0] | ((uint16_t)bytes[1] << 8U));
}

static uint32_t read_u32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8U) |
           ((uint32_t)bytes[2] << 16U) | ((uint32_t)bytes[3] << 24U);
}

static int range_valid(uint32_t offset, uint32_t size, uint32_t total) {
    return offset <= total && size <= total - offset;
}

static int table_valid(uint32_t offset, uint32_t count, uint32_t item_size,
                       uint32_t total) {
    if (count != 0U && offset < D2E_XIP_HEADER_SIZE) {
        return 0;
    }
    return count <= UINT32_MAX / item_size &&
           range_valid(offset, count * item_size, total);
}

static int field_string(char *output, size_t output_size,
                        const uint8_t *input) {
    const void *const terminator = memchr(input, 0, output_size);
    size_t length;
    if (terminator == NULL) {
        return 0;
    }
    length = (size_t)((const uint8_t *)terminator - input);
    memcpy(output, input, length + 1U);
    if (length + 1U < output_size) {
        memset(output + length + 1U, 0, output_size - length - 1U);
    }
    return 1;
}

static int valid_command(const char *command) {
    size_t index;
    const size_t length = strlen(command);
    if (length == 0U || length > D2E_PACKAGE_COMMAND_MAX) {
        return 0;
    }
    for (index = 0U; index < length; ++index) {
        const unsigned char character = (unsigned char)command[index];
        if (!isalnum(character) && character != '_') {
            return 0;
        }
    }
    return 1;
}

static int in_mapped_segment(const d2e_xip_manifest *manifest,
                             uint32_t offset, uint32_t size) {
    return (offset >= manifest->irom_offset &&
            range_valid(offset - manifest->irom_offset, size,
                        manifest->irom_size)) ||
           (offset >= manifest->drom_offset &&
            range_valid(offset - manifest->drom_offset, size,
                        manifest->drom_size));
}

int d2e_xip_relocation_at(const d2e_xip_module_view *view, size_t index,
                          d2e_xip_relocation *relocation) {
    const uint8_t *record;
    if (view == NULL || relocation == NULL ||
        index >= view->manifest.relocation_count) {
        return 0;
    }
    record = view->bytes + view->manifest.relocation_offset +
             index * D2E_XIP_RELOCATION_SIZE;
    relocation->patch_offset = read_u32(record);
    relocation->target_kind = (d2e_xip_target_kind)read_u32(record + 4U);
    relocation->target = read_u32(record + 8U);
    relocation->addend = (int32_t)read_u32(record + 12U);
    return 1;
}

int d2e_xip_fragment_at(const d2e_xip_module_view *view, size_t index,
                        d2e_xip_fragment *fragment) {
    const uint8_t *record;
    if (view == NULL || fragment == NULL ||
        index >= view->manifest.fragment_count) {
        return 0;
    }
    record = view->bytes + view->manifest.fragment_offset +
             index * D2E_XIP_FRAGMENT_SIZE;
    fragment->image_offset = read_u32(record);
    fragment->data_offset = read_u32(record + 4U);
    fragment->size = read_u32(record + 8U);
    return 1;
}

int d2e_xip_mz_relocation_at(const d2e_xip_module_view *view, size_t index,
                             d2e_mz_relocation *relocation) {
    const uint8_t *record;
    if (view == NULL || relocation == NULL ||
        index >= view->manifest.mz_relocation_count) {
        return 0;
    }
    record = view->bytes + view->manifest.mz_relocation_offset +
             index * D2E_XIP_MZ_RELOCATION_SIZE;
    relocation->offset = read_u16(record);
    relocation->segment = read_u16(record + 2U);
    return 1;
}

static int validate_records(const d2e_xip_module_view *view) {
    size_t index;
    uint32_t previous_image_end = 0U;
    for (index = 0U; index < view->manifest.relocation_count; ++index) {
        d2e_xip_relocation relocation;
        (void)d2e_xip_relocation_at(view, index, &relocation);
        if ((relocation.patch_offset & 3U) != 0U ||
            !in_mapped_segment(&view->manifest, relocation.patch_offset, 4U) ||
            relocation.target_kind > D2E_XIP_TARGET_IMPORT ||
            ((relocation.target_kind == D2E_XIP_TARGET_IROM &&
              relocation.target >= view->manifest.irom_size) ||
             (relocation.target_kind == D2E_XIP_TARGET_DROM &&
              relocation.target >= view->manifest.drom_size))) {
            return 0;
        }
    }
    for (index = 0U; index < view->manifest.fragment_count; ++index) {
        d2e_xip_fragment fragment;
        (void)d2e_xip_fragment_at(view, index, &fragment);
        if (fragment.size == 0U || fragment.image_offset < previous_image_end ||
            !range_valid(fragment.image_offset, fragment.size,
                         view->manifest.image_size) ||
            !range_valid(fragment.data_offset, fragment.size,
                         view->manifest.module_size) ||
            fragment.data_offset < view->manifest.drom_offset ||
            !range_valid(fragment.data_offset - view->manifest.drom_offset,
                         fragment.size, view->manifest.drom_size)) {
            return 0;
        }
        previous_image_end = fragment.image_offset + fragment.size;
    }
    return 1;
}

int d2e_xip_module_open(d2e_xip_module_view *view, const void *bytes,
                        size_t byte_count) {
    const uint8_t *data = (const uint8_t *)bytes;
    d2e_xip_manifest *manifest;
    if (view == NULL || data == NULL || byte_count < D2E_XIP_HEADER_SIZE ||
        memcmp(data, module_magic, sizeof(module_magic)) != 0 ||
        read_u32(data + 8U) != D2E_XIP_FORMAT_VERSION ||
        read_u32(data + 12U) != D2E_XIP_HEADER_SIZE ||
        read_u32(data + 16U) != D2E_PACKAGE_ABI_VERSION ||
        read_u32(data + 20U) != D2E_XIP_SHELL_ABI_VERSION) {
        return 0;
    }
    memset(view, 0, sizeof(*view));
    view->bytes = data;
    view->byte_count = byte_count;
    manifest = &view->manifest;
    manifest->flags = read_u32(data + 24U);
    manifest->module_size = read_u32(data + 28U);
    manifest->irom_offset = read_u32(data + 32U);
    manifest->irom_size = read_u32(data + 36U);
    manifest->drom_offset = read_u32(data + 40U);
    manifest->drom_size = read_u32(data + 44U);
    manifest->relocation_offset = read_u32(data + 48U);
    manifest->relocation_count = read_u32(data + 52U);
    manifest->region_offset = read_u32(data + 56U);
    manifest->image_size = read_u32(data + 60U);
    manifest->fragment_offset = read_u32(data + 64U);
    manifest->fragment_count = read_u32(data + 68U);
    manifest->mz_relocation_offset = read_u32(data + 72U);
    manifest->mz_relocation_count = read_u32(data + 76U);
    manifest->image_format = (d2e_native_image_format)read_u32(data + 80U);
    manifest->load_segment = read_u16(data + 84U);
    manifest->entry_cs = read_u16(data + 86U);
    manifest->entry_ip = read_u16(data + 88U);
    manifest->initial_ss = read_u16(data + 90U);
    manifest->initial_sp = read_u16(data + 92U);
    if (!field_string(manifest->command, sizeof(manifest->command),
                      data + 100U) ||
        !field_string(manifest->name, sizeof(manifest->name), data + 109U) ||
        !field_string(manifest->title, sizeof(manifest->title), data + 141U)) {
        return 0;
    }
    memcpy(manifest->sha256, data + 205U, sizeof(manifest->sha256));

    if (manifest->flags != 0U ||
        manifest->module_size > byte_count ||
        manifest->module_size < D2E_XIP_HEADER_SIZE ||
        manifest->irom_offset % D2E_XIP_FLASH_PAGE_SIZE != 0U ||
        manifest->drom_offset % D2E_XIP_FLASH_PAGE_SIZE != 0U ||
        manifest->irom_size == 0U || manifest->drom_size == 0U ||
        !range_valid(manifest->irom_offset, manifest->irom_size,
                     manifest->module_size) ||
        !range_valid(manifest->drom_offset, manifest->drom_size,
                     manifest->module_size) ||
        manifest->region_offset >= manifest->irom_size ||
        !table_valid(manifest->relocation_offset,
                     manifest->relocation_count, D2E_XIP_RELOCATION_SIZE,
                     manifest->module_size) ||
        !table_valid(manifest->fragment_offset, manifest->fragment_count,
                     D2E_XIP_FRAGMENT_SIZE, manifest->module_size) ||
        !table_valid(manifest->mz_relocation_offset,
                     manifest->mz_relocation_count,
                     D2E_XIP_MZ_RELOCATION_SIZE, manifest->module_size) ||
        (manifest->image_format != D2E_NATIVE_IMAGE_COM &&
         manifest->image_format != D2E_NATIVE_IMAGE_MZ) ||
        !valid_command(manifest->command) || manifest->name[0] == 0 ||
        manifest->title[0] == 0 || !validate_records(view)) {
        memset(view, 0, sizeof(*view));
        return 0;
    }
    return 1;
}
