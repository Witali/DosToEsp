#include "d2e/pc_speaker.h"

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

static void check_samples(const uint8_t *actual, const uint8_t *expected,
                          size_t count) {
    CHECK(memcmp(actual, expected, count) == 0);
}

int main(void) {
    d2e_pc_speaker_synth synth;
    d2e_pc_speaker_control control = {1U, 4U, 3U, 1U, 1U};
    uint8_t samples[8];
    const uint8_t square[8] = {
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_LOW, D2E_PC_SPEAKER_LOW,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_LOW, D2E_PC_SPEAKER_LOW};
    const uint8_t rate[8] = {
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_LOW,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_LOW};
    const uint8_t one_shot[8] = {
        D2E_PC_SPEAKER_LOW, D2E_PC_SPEAKER_LOW,
        D2E_PC_SPEAKER_LOW, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH,
        D2E_PC_SPEAKER_HIGH, D2E_PC_SPEAKER_HIGH};

    d2e_pc_speaker_synth_init(&synth, D2E_PIT_INPUT_HZ);
    d2e_pc_speaker_render(&synth, &control, samples, sizeof(samples));
    check_samples(samples, square, sizeof(samples));
    CHECK(d2e_pc_speaker_frequency_hz(&control) == UINT32_C(298296));

    control.generation++;
    control.mode = 2U;
    d2e_pc_speaker_render(&synth, &control, samples, sizeof(samples));
    check_samples(samples, rate, sizeof(samples));

    control.generation++;
    control.reload = 3U;
    control.mode = 0U;
    d2e_pc_speaker_render(&synth, &control, samples, sizeof(samples));
    check_samples(samples, one_shot, sizeof(samples));

    control.generation++;
    control.speaker_data = 0U;
    d2e_pc_speaker_render(&synth, &control, samples, sizeof(samples));
    {
        uint8_t silence[sizeof(samples)];
        memset(silence, D2E_PC_SPEAKER_SILENCE, sizeof(silence));
        check_samples(samples, silence, sizeof(samples));
    }

    control.reload = 0U;
    CHECK(d2e_pc_speaker_divisor(&control) == UINT32_C(65536));
    CHECK(d2e_pc_speaker_frequency_hz(&control) == UINT32_C(18));

    if (failures != 0U) {
        fprintf(stderr, "%u PC speaker test(s) failed\n", failures);
        return 1;
    }
    puts("PC speaker synthesis tests passed");
    return 0;
}
