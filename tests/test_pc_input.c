#include "d2e/pc_input.h"

#include <stdio.h>
#include <string.h>

static unsigned failures;

#define CHECK(expression)                                                       \
    do {                                                                        \
        if (!(expression)) {                                                    \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__,  \
                    #expression);                                               \
            ++failures;                                                         \
        }                                                                       \
    } while (0)

static uint16_t take_key(d2e_pc_at *machine) {
    const d2e_pc_at_key key = machine->key_queue[machine->key_head];
    machine->key_head =
        (uint8_t)((machine->key_head + 1U) % D2E_PC_AT_KEY_QUEUE_CAPACITY);
    --machine->key_count;
    return (uint16_t)(((uint16_t)key.scan << 8U) | key.ascii);
}

int main(void) {
    d2e_pc_at machine;
    d2e_pc_input input;

    memset(&machine, 0, sizeof(machine));
    d2e_pc_input_init(&input);
    CHECK(d2e_pc_input_feed_byte(&input, &machine, UINT8_C('A')));
    CHECK(d2e_pc_input_feed_byte(&input, &machine, UINT8_C('0')));
    CHECK(d2e_pc_input_feed_byte(&input, &machine, UINT8_C(' ')));
    CHECK(machine.scan_count == 6U);
    CHECK(machine.scan_queue[0] == UINT8_C(0x1e));
    CHECK(machine.scan_queue[1] == UINT8_C(0x9e));
    CHECK(take_key(&machine) == UINT16_C(0x1e41));
    CHECK(take_key(&machine) == UINT16_C(0x0b30));
    CHECK(take_key(&machine) == UINT16_C(0x3920));

    CHECK(!d2e_pc_input_feed_byte(&input, &machine, UINT8_C(0x1b)));
    CHECK(!d2e_pc_input_feed_byte(&input, &machine, UINT8_C('[')));
    CHECK(d2e_pc_input_feed_byte(&input, &machine, UINT8_C('D')));
    CHECK(take_key(&machine) == UINT16_C(0x4b00));
    CHECK(d2e_pc_input_feed_byte(&input, &machine, UINT8_C('`')));
    CHECK(take_key(&machine) == UINT16_C(0x011b));

    if (failures != 0U) {
        fprintf(stderr, "%u PC input test(s) failed\n", failures);
        return 1;
    }
    puts("PC keyboard input mapping tests passed");
    return 0;
}
