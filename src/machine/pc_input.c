#include "d2e/pc_input.h"

#include <string.h>

static uint8_t letter_scan(uint8_t lower) {
    static const char keys[] = "qwertyuiopasdfghjklzxcvbnm";
    static const uint8_t scans[] = {
        0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
        0x19, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25,
        0x26, 0x2c, 0x2d, 0x2e, 0x2f, 0x30, 0x31, 0x32,
    };
    size_t index;
    for (index = 0U; index < sizeof(keys) - 1U; ++index) {
        if ((uint8_t)keys[index] == lower) {
            return scans[index];
        }
    }
    return 0U;
}

static int feed_plain(d2e_pc_at *machine, uint8_t byte) {
    uint8_t scan = 0U;
    uint8_t ascii = byte;
    uint8_t lower = byte;
    if (byte >= UINT8_C('A') && byte <= UINT8_C('Z')) {
        lower = (uint8_t)(byte + (UINT8_C('a') - UINT8_C('A')));
    }
    if (lower >= UINT8_C('a') && lower <= UINT8_C('z')) {
        scan = letter_scan(lower);
    } else if (byte >= UINT8_C('1') && byte <= UINT8_C('9')) {
        scan = (uint8_t)(byte - UINT8_C('1') + 2U);
    } else if (byte == UINT8_C('0')) {
        scan = UINT8_C(0x0b);
    } else if (byte == UINT8_C(' ')) {
        scan = UINT8_C(0x39);
    } else if (byte == UINT8_C('\r') || byte == UINT8_C('\n')) {
        ascii = UINT8_C('\r');
        scan = UINT8_C(0x1c);
    } else if (byte == UINT8_C('\b') || byte == UINT8_C(0x7f)) {
        ascii = UINT8_C('\b');
        scan = UINT8_C(0x0e);
    } else if (byte == UINT8_C('\t')) {
        scan = UINT8_C(0x0f);
    } else if (byte == UINT8_C('`')) {
        ascii = UINT8_C(0x1b);
        scan = UINT8_C(0x01);
    }
    return scan != 0U ? d2e_pc_at_enqueue_key(machine, ascii, scan) : 0;
}

void d2e_pc_input_init(d2e_pc_input *input) {
    memset(input, 0, sizeof(*input));
}

int d2e_pc_input_feed_byte(d2e_pc_input *input, d2e_pc_at *machine,
                           uint8_t byte) {
    if (input == NULL || machine == NULL) {
        return 0;
    }
    if (input->escape_state == 0U) {
        if (byte == UINT8_C(0x1b)) {
            input->escape_state = 1U;
            return 0;
        }
        return feed_plain(machine, byte);
    }
    if (input->escape_state == 1U) {
        input->escape_state = byte == UINT8_C('[') ? 2U : 0U;
        return 0;
    }
    input->escape_state = 0U;
    switch (byte) {
        case 'A':
            return d2e_pc_at_enqueue_key(machine, 0U, UINT8_C(0x48));
        case 'B':
            return d2e_pc_at_enqueue_key(machine, 0U, UINT8_C(0x50));
        case 'C':
            return d2e_pc_at_enqueue_key(machine, 0U, UINT8_C(0x4d));
        case 'D':
            return d2e_pc_at_enqueue_key(machine, 0U, UINT8_C(0x4b));
        default:
            return 0;
    }
}
