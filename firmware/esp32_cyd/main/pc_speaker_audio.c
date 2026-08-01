#include "pc_speaker_audio.h"

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>

#include "board_config.h"
#include "driver/dac_continuous.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum {
    SPEAKER_RENDER_SAMPLES = 64,
    SPEAKER_DMA_BUFFER_BYTES = 512,
    SPEAKER_DMA_DESCRIPTORS = 6,
    SPEAKER_EVENT_CAPACITY = 256,
    SPEAKER_EVENT_LATENCY_US = 32000,
    SPEAKER_LATE_EVENT_US = 1000,
    SPEAKER_STATS_INTERVAL_US = 5000000,
    SPEAKER_TASK_STACK_BYTES = 3072,
    SPEAKER_TASK_PRIORITY = 5,
};

typedef struct speaker_event {
    d2e_pc_speaker_control control;
    uint64_t timestamp_us;
} speaker_event;

static dac_continuous_handle_t speaker_dac;
static portMUX_TYPE speaker_lock = portMUX_INITIALIZER_UNLOCKED;
static speaker_event speaker_events[SPEAKER_EVENT_CAPACITY];
static uint16_t speaker_event_head;
static uint16_t speaker_event_count;
static uint32_t speaker_events_received;
static uint32_t speaker_queue_overruns;
static uint16_t speaker_queue_high_water;
static uint8_t logged_active;

static int dequeue_speaker_event(speaker_event *event) {
    int available = 0;
    portENTER_CRITICAL(&speaker_lock);
    if (speaker_event_count != 0U) {
        *event = speaker_events[speaker_event_head];
        speaker_event_head =
            (uint16_t)((speaker_event_head + 1U) % SPEAKER_EVENT_CAPACITY);
        --speaker_event_count;
        available = 1;
    }
    portEXIT_CRITICAL(&speaker_lock);
    return available;
}

static void update_speaker(void *context,
                           const d2e_pc_speaker_control *control) {
    const uint64_t timestamp_us = (uint64_t)esp_timer_get_time();
    uint16_t tail;
    (void)context;
    portENTER_CRITICAL(&speaker_lock);
    if (speaker_event_count == SPEAKER_EVENT_CAPACITY) {
        speaker_event_head =
            (uint16_t)((speaker_event_head + 1U) % SPEAKER_EVENT_CAPACITY);
        --speaker_event_count;
        ++speaker_queue_overruns;
    }
    tail = (uint16_t)((speaker_event_head + speaker_event_count) %
                      SPEAKER_EVENT_CAPACITY);
    speaker_events[tail].control = *control;
    speaker_events[tail].timestamp_us = timestamp_us;
    ++speaker_event_count;
    ++speaker_events_received;
    if (speaker_event_count > speaker_queue_high_water) {
        speaker_queue_high_water = speaker_event_count;
    }
    portEXIT_CRITICAL(&speaker_lock);

    if (logged_active == 0U && control->gate != 0U &&
        control->speaker_data != 0U) {
        logged_active = 1U;
        esp_rom_printf(
            "D2E_AUDIO_ACTIVE,mode=%u,divisor=%" PRIu32 ",hz=%" PRIu32
            "\n",
            (unsigned)control->mode, d2e_pc_speaker_divisor(control),
            d2e_pc_speaker_frequency_hz(control));
    }
}

static void speaker_task(void *argument) {
    d2e_pc_speaker_synth synth;
    d2e_pc_speaker_control control = {0};
    speaker_event next_event;
    uint8_t samples[SPEAKER_RENDER_SAMPLES];
    uint64_t render_time_us;
    uint32_t render_fraction_q32 = 0U;
    const uint64_t sample_step_q32 =
        (UINT64_C(1000000) << 32U) / D2E_PC_SPEAKER_SAMPLE_RATE;
    uint64_t last_stats_us;
    uint32_t events_applied = 0U;
    uint32_t late_events = 0U;
    uint32_t dac_errors = 0U;
    int have_next_event;
    (void)argument;
    d2e_pc_speaker_synth_init(&synth, D2E_PC_SPEAKER_SAMPLE_RATE);
    last_stats_us = (uint64_t)esp_timer_get_time();
    render_time_us = last_stats_us > SPEAKER_EVENT_LATENCY_US
                         ? last_stats_us - SPEAKER_EVENT_LATENCY_US
                         : 0U;
    have_next_event = dequeue_speaker_event(&next_event);

    for (;;) {
        size_t index;
        size_t offset = 0U;
        const uint64_t now_us = (uint64_t)esp_timer_get_time();
        if (render_time_us + SPEAKER_EVENT_LATENCY_US > now_us + 1000U) {
            const uint64_t wait_us =
                render_time_us + SPEAKER_EVENT_LATENCY_US - now_us;
            vTaskDelay(pdMS_TO_TICKS((wait_us + 999U) / 1000U));
        }
        if (!have_next_event) {
            have_next_event = dequeue_speaker_event(&next_event);
        }

        for (index = 0U; index < sizeof(samples); ++index) {
            const uint64_t sample_time_us = render_time_us;
            const uint64_t fraction_sum =
                (uint64_t)render_fraction_q32 +
                (uint32_t)sample_step_q32;
            while (have_next_event &&
                   next_event.timestamp_us <= sample_time_us) {
                if (sample_time_us >
                    next_event.timestamp_us + SPEAKER_LATE_EVENT_US) {
                    ++late_events;
                }
                control = next_event.control;
                ++events_applied;
                have_next_event = dequeue_speaker_event(&next_event);
            }
            d2e_pc_speaker_render(&synth, &control, samples + index, 1U);
            render_time_us +=
                (sample_step_q32 >> 32U) + (fraction_sum >> 32U);
            render_fraction_q32 = (uint32_t)fraction_sum;
        }

        while (offset < sizeof(samples)) {
            size_t written = 0U;
            const esp_err_t result = dac_continuous_write(
                speaker_dac, samples + offset, sizeof(samples) - offset,
                &written, 1000);
            offset += written;
            if (result != ESP_OK || written == 0U) {
                ++dac_errors;
                vTaskDelay(pdMS_TO_TICKS(1));
            }
        }

        if ((uint64_t)esp_timer_get_time() - last_stats_us >=
            SPEAKER_STATS_INTERVAL_US) {
            uint16_t queued;
            uint16_t high_water;
            uint32_t received;
            uint32_t overruns;
            portENTER_CRITICAL(&speaker_lock);
            queued = speaker_event_count;
            high_water = speaker_queue_high_water;
            received = speaker_events_received;
            overruns = speaker_queue_overruns;
            portEXIT_CRITICAL(&speaker_lock);
            esp_rom_printf(
                "D2E_AUDIO_STATS,received=%" PRIu32 ",applied=%" PRIu32
                ",queued=%u,high_water=%u,overruns=%" PRIu32
                ",late=%" PRIu32 ",dac_errors=%" PRIu32 "\n",
                received, events_applied, (unsigned)queued,
                (unsigned)high_water, overruns, late_events, dac_errors);
            last_stats_us = (uint64_t)esp_timer_get_time();
        }
    }
}

esp_err_t pc_speaker_audio_init(d2e_pc_at *machine) {
    dac_continuous_config_t config = {0};
    BaseType_t task_result;
    esp_err_t result;

    config.chan_mask = DAC_CHANNEL_MASK_CH1;
    config.desc_num = SPEAKER_DMA_DESCRIPTORS;
    config.buf_size = SPEAKER_DMA_BUFFER_BYTES;
    config.freq_hz = D2E_PC_SPEAKER_SAMPLE_RATE;
    config.offset = 0;
    config.clk_src = DAC_DIGI_CLK_SRC_APLL;
    config.chan_mode = DAC_CHANNEL_MODE_SIMUL;
    result = dac_continuous_new_channels(&config, &speaker_dac);
    if (result != ESP_OK) {
        return result;
    }
    result = dac_continuous_enable(speaker_dac);
    if (result != ESP_OK) {
        (void)dac_continuous_del_channels(speaker_dac);
        speaker_dac = NULL;
        return result;
    }

    d2e_pc_at_set_speaker_callback(machine, NULL, update_speaker);
    task_result = xTaskCreatePinnedToCore(
        speaker_task, "pc-speaker", SPEAKER_TASK_STACK_BYTES, NULL,
        SPEAKER_TASK_PRIORITY, NULL, 0);
    if (task_result != pdPASS) {
        d2e_pc_at_set_speaker_callback(machine, NULL, NULL);
        (void)dac_continuous_disable(speaker_dac);
        (void)dac_continuous_del_channels(speaker_dac);
        speaker_dac = NULL;
        return ESP_ERR_NO_MEM;
    }

    esp_rom_printf("D2E_AUDIO_READY,rate=%" PRIu32 ",gpio=%u\n",
                   D2E_PC_SPEAKER_SAMPLE_RATE,
                   (unsigned)BOARD_AUDIO_DAC);
    return ESP_OK;
}
