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

static uint8_t punctuation_scan(uint8_t byte) {
    static const char keys[] = "-_=+[{]};:'\"`~\\|,<.>/?";
    static const uint8_t scans[] = {
        0x0c, 0x0c, 0x0d, 0x0d, 0x1a, 0x1a, 0x1b, 0x1b,
        0x27, 0x27, 0x28, 0x28, 0x29, 0x29, 0x2b, 0x2b,
        0x33, 0x33, 0x34, 0x34, 0x35, 0x35,
    };
    size_t index;
    for (index = 0U; index < sizeof(keys) - 1U; ++index) {
        if ((uint8_t)keys[index] == byte) {
            return scans[index];
        }
    }
    return 0U;
}

static uint8_t shifted_digit_scan(uint8_t byte) {
    static const char keys[] = "!@#$%^&*()";
    static const uint8_t scans[] = {
        0x02, 0x03, 0x04, 0x05, 0x06,
        0x07, 0x08, 0x09, 0x0a, 0x0b,
    };
    size_t index;
    for (index = 0U; index < sizeof(keys) - 1U; ++index) {
        if ((uint8_t)keys[index] == byte) {
            return scans[index];
        }
    }
    return 0U;
}

static int feed_plain(d2e_pc_at *machine, uint8_t byte) {
    uint8_t scan = 0U;
    uint8_t ascii = byte;
    uint8_t lower = byte;
    if (byte >= 1U && byte <= 26U) {
        lower = (uint8_t)(UINT8_C('a') + byte - 1U);
    } else if (byte >= UINT8_C('A') && byte <= UINT8_C('Z')) {
        lower = (uint8_t)(byte + (UINT8_C('a') - UINT8_C('A')));
    }
    if (lower >= UINT8_C('a') && lower <= UINT8_C('z')) {
        scan = letter_scan(lower);
    } else if (byte >= UINT8_C('1') && byte <= UINT8_C('9')) {
        scan = (uint8_t)(byte - UINT8_C('1') + 2U);
    } else if (byte == UINT8_C('0')) {
        scan = UINT8_C(0x0b);
    } else if ((scan = shifted_digit_scan(byte)) != 0U) {
        /* The ASCII byte already identifies the shifted key. */
    } else if ((scan = punctuation_scan(byte)) != 0U) {
        /* The ASCII byte already identifies the shifted key. */
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
    } else if (byte == UINT8_C(0x1b)) {
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
        if (byte == UINT8_C('[')) {
            input->escape_state = 2U;
            return 0;
        }
        input->escape_state = 0U;
        if (byte == UINT8_C(0x1b)) {
            return feed_plain(machine, byte);
        }
        {
            const int escape_handled =
                feed_plain(machine, UINT8_C(0x1b));
            const int byte_handled = feed_plain(machine, byte);
            return escape_handled || byte_handled;
        }
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
