/* SPDX-License-Identifier: GPL-2.0 */
/*
 * WCD939x baseline static reconstruction (Variant 0).
 * LA donor: track_b_corpora/audio-kernel-ar/asoc/codecs/wcd939x/
 */

#ifndef __WCD939X_BASELINE_H__
#define __WCD939X_BASELINE_H__

#include <linux/bitops.h>
#include <linux/device.h>
#include <linux/regmap.h>
#include <sound/soc.h>

#define WCD939X_MAX_REGISTER      0x3FFF
#define WCD939X_CODEC_RATES       (SNDRV_PCM_RATE_8000 | SNDRV_PCM_RATE_16000 |                                    SNDRV_PCM_RATE_32000 | SNDRV_PCM_RATE_48000)
#define WCD939X_CODEC_FORMATS     (SNDRV_PCM_FMTBIT_S16_LE | SNDRV_PCM_FMTBIT_S24_LE)

enum wcd939x_sdw_ports {
    WCD939X_HPH_PORT = 1,
    WCD939X_ADC_PORT,
    WCD939X_DMIC_PORT,
    WCD939X_MBHC_PORT,
};

struct wcd939x_sdw_priv {
    struct device *dev;
    struct regmap *regmap;
    bool is_tx;
    bool is_rx;
};

struct wcd939x_priv {
    struct device *dev;
    struct regmap *regmap;
    struct snd_soc_component *component;
    struct device_node *rxnode;
    struct device_node *txnode;
    struct device *rxdev;
    struct device *txdev;
};

int wcd939x_sdw_hw_params(struct wcd939x_sdw_priv *wcd,
                          struct snd_pcm_substream *substream,
                          struct snd_pcm_hw_params *params,
                          struct snd_soc_dai *dai);
int wcd939x_sdw_free(struct wcd939x_sdw_priv *wcd,
                     struct snd_pcm_substream *substream,
                     struct snd_soc_dai *dai);
int wcd939x_sdw_set_sdw_stream(struct wcd939x_sdw_priv *wcd,
                               struct snd_soc_dai *dai,
                               void *stream,
                               int direction);

#endif /* __WCD939X_BASELINE_H__ */
