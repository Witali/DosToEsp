#include "pc_speaker_audio.h"

#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>

#include "board_config.h"
#include "driver/dac_continuous.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

enum {
    SPEAKER_DMA_SAMPLES = 256,
    SPEAKER_DMA_BYTES = SPEAKER_DMA_SAMPLES * 2,
    SPEAKER_DMA_DESCRIPTORS = 4,
    SPEAKER_TASK_STACK_BYTES = 3072,
    SPEAKER_TASK_PRIORITY = 5,
};

static dac_continuous_handle_t speaker_dac;
static portMUX_TYPE speaker_lock = portMUX_INITIALIZER_UNLOCKED;
static d2e_pc_speaker_control pending_control;
static uint8_t logged_active;

static void update_speaker(void *context,
                           const d2e_pc_speaker_control *control) {
    (void)context;
    portENTER_CRITICAL(&speaker_lock);
    pending_control = *control;
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
    uint8_t samples[SPEAKER_DMA_SAMPLES];
    (void)argument;
    d2e_pc_speaker_synth_init(&synth, D2E_PC_SPEAKER_SAMPLE_RATE);

    for (;;) {
        d2e_pc_speaker_control control;
        size_t offset = 0U;
        portENTER_CRITICAL(&speaker_lock);
        control = pending_control;
        portEXIT_CRITICAL(&speaker_lock);
        d2e_pc_speaker_render(&synth, &control, samples, sizeof(samples));

        while (offset < sizeof(samples)) {
            size_t written = 0U;
            const esp_err_t result = dac_continuous_write(
                speaker_dac, samples + offset, sizeof(samples) - offset,
                &written, 1000);
            if (result != ESP_OK || written == 0U) {
                vTaskDelay(pdMS_TO_TICKS(1));
                break;
            }
            offset += written;
        }
    }
}

esp_err_t pc_speaker_audio_init(d2e_pc_at *machine) {
    dac_continuous_config_t config = {0};
    BaseType_t task_result;
    esp_err_t result;

    config.chan_mask = DAC_CHANNEL_MASK_CH1;
    config.desc_num = SPEAKER_DMA_DESCRIPTORS;
    config.buf_size = SPEAKER_DMA_BYTES;
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
