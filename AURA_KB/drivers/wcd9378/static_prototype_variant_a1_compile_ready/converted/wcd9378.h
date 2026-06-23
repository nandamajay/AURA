/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * RFC static prototype header for Qualcomm WCD9378 codec family integration.
 */

#ifndef _WCD9378_STATIC_PROTOTYPE_H
#define _WCD9378_STATIC_PROTOTYPE_H

#include <linux/errno.h>
#include <linux/bitops.h>
#include <linux/component.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/regmap.h>
#include <linux/regulator/consumer.h>
#include <linux/soundwire/sdw.h>
#include <linux/soundwire/sdw_type.h>
#include <sound/soc.h>
#include "wcd-common.h"
#include "wcd-mbhc-v2.h"

#define WCD9378_DRV_NAME                       "wcd9378-codec"

/*
 * Downstream register model exposes a high analog domain via 0x40180000.
 * Static prototype keeps this encoded for lineage; runtime behavior remains gated.
 */
#define WCD9378_BASE                            0x3fffffff
#define WCD9378_A_BASE                          (WCD9378_BASE + 0x180001)

/* Digital register subset required by static lifecycle scaffold. */
#define WCD9378_BASE_ADDRESS                    0x3000
#define WCD9378_ANA_BIAS                        0x3001
#define WCD9378_ANA_MBHC_RESULT_1               0x3017
#define WCD9378_ANA_MBHC_RESULT_2               0x3018
#define WCD9378_ANA_MBHC_RESULT_3               0x3019
#define WCD9378_MBHC_MOISTURE_DET_FSM_STATUS    0x305b
#define WCD9378_TX_1_2_SAR1_ERR                 0x3086
#define WCD9378_TX_1_2_SAR2_ERR                 0x3085
#define WCD9378_HPH_L_STATUS                    0x30c9
#define WCD9378_HPH_R_STATUS                    0x30ca
#define WCD9378_HPH_SURGE_HPHLR_SURGE_STATUS    0x30e4
#define WCD9378_EAR_STATUS_REG_1                0x30ef
#define WCD9378_EAR_STATUS_REG_2                0x30f0
#define WCD9378_MBHC_NEW_FSM_STATUS             0x3125
#define WCD9378_MBHC_NEW_ADC_RESULT             0x3126
#define WCD9378_DIE_CRACK_DIE_CRK_DET_OUT       0x312d
#define WCD9378_DIGITAL_INTR_MASK_0             0x346b
#define WCD9378_DIGITAL_INTR_MASK_1             0x346c
#define WCD9378_DIGITAL_INTR_MASK_2             0x346d
#define WCD9378_DIGITAL_INTR_STATUS_0           0x346e
#define WCD9378_DIGITAL_INTR_STATUS_1           0x346f
#define WCD9378_DIGITAL_INTR_STATUS_2           0x3470
#define WCD9378_DIGITAL_INTR_CLEAR_0            0x3471
#define WCD9378_DIGITAL_INTR_CLEAR_1            0x3472
#define WCD9378_DIGITAL_INTR_CLEAR_2            0x3473
#define WCD9378_DIGITAL_EFUSE_REG_0             0x34b0
#define WCD9378_DIGITAL_EFUSE_REG_31            0x34cf
#define WCD9378_MAX_REGISTER                    WCD9378_DIGITAL_EFUSE_REG_31

/* Hardware-confirmed SoundWire identity from ELIZA EVK evidence logs. */
#define WCD9378_SDW_PART_ID                     0x110
#define WCD9378_SDW_COMPATIBLE                  "sdw20217011000"

#define WCD9378_MAX_MICBIAS                     3
#define WCD9378_MAX_TX_CHANNELS                 13
#define WCD9378_MAX_RX_CHANNELS                 8
#define WCD9378_MAX_SWR_CH_IDS                  16
#define WCD9378_SWRM_CH_MASK(ch_idx)            BIT((ch_idx) - 1)

#define WCD9378_RATES                           (SNDRV_PCM_RATE_8000 | SNDRV_PCM_RATE_16000 | \
					 SNDRV_PCM_RATE_32000 | SNDRV_PCM_RATE_48000 | \
					 SNDRV_PCM_RATE_96000 | SNDRV_PCM_RATE_192000 | \
					 SNDRV_PCM_RATE_384000)
#define WCD9378_FRAC_RATES                      (SNDRV_PCM_RATE_44100 | SNDRV_PCM_RATE_88200 | \
					 SNDRV_PCM_RATE_176400 | SNDRV_PCM_RATE_352800)
#define WCD9378_FORMATS                         (SNDRV_PCM_FMTBIT_S16_LE | \
						 SNDRV_PCM_FMTBIT_S24_LE | \
						 SNDRV_PCM_FMTBIT_S24_3LE | \
						 SNDRV_PCM_FMTBIT_S32_LE)

enum wcd9378_codec_dai_id {
	AIF1_PB = 0,
	AIF1_CAP,
	NUM_CODEC_DAIS,
};

enum wcd9378_tx_sdw_ports {
	WCD9378_ADC_1_PORT = 1,
	WCD9378_ADC_2_3_PORT,
	WCD9378_DMIC_0_3_MBHC_PORT,
	WCD9378_DMIC_4_7_PORT,
	WCD9378_MAX_TX_SWR_PORTS = WCD9378_DMIC_4_7_PORT,
};

enum wcd9378_rx_sdw_ports {
	WCD9378_HPH_PORT = 1,
	WCD9378_CLSH_PORT,
	WCD9378_COMP_PORT,
	WCD9378_LO_PORT,
	WCD9378_DSD_PORT,
	WCD9378_MAX_SWR_PORTS = WCD9378_DSD_PORT,
};

enum wcd9378_tx_sdw_channels {
	WCD9378_ADC1,
	WCD9378_ADC2,
	WCD9378_ADC3,
	WCD9378_ADC4,
	WCD9378_DMIC0,
	WCD9378_DMIC1,
	WCD9378_MBHC,
	WCD9378_DMIC2,
	WCD9378_DMIC3,
	WCD9378_DMIC4,
	WCD9378_DMIC5,
	WCD9378_DMIC6,
	WCD9378_DMIC7,
};

enum wcd9378_rx_sdw_channels {
	WCD9378_HPH_L,
	WCD9378_HPH_R,
	WCD9378_CLSH,
	WCD9378_COMP_L,
	WCD9378_COMP_R,
	WCD9378_LO,
	WCD9378_DSD_R,
	WCD9378_DSD_L,
};

enum {
	WCD9378_IRQ_MBHC_BUTTON_PRESS_DET = 0,
	WCD9378_IRQ_MBHC_BUTTON_RELEASE_DET,
	WCD9378_IRQ_MBHC_ELECT_INS_REM_DET,
	WCD9378_IRQ_MBHC_ELECT_INS_REM_LEG_DET,
	WCD9378_IRQ_MBHC_SW_DET,
	WCD9378_IRQ_HPHR_OCP_INT,
	WCD9378_IRQ_HPHR_CNP_INT,
	WCD9378_IRQ_HPHL_OCP_INT,
	WCD9378_IRQ_HPHL_CNP_INT,
	WCD9378_IRQ_EAR_CNP_INT,
	WCD9378_IRQ_EAR_SCD_INT,
	WCD9378_IRQ_AUX_CNP_INT,
	WCD9378_IRQ_AUX_SCD_INT,
	WCD9378_IRQ_HPHL_PDM_WD_INT,
	WCD9378_IRQ_HPHR_PDM_WD_INT,
	WCD9378_IRQ_AUX_PDM_WD_INT,
	WCD9378_IRQ_LDORT_SCD_INT,
	WCD9378_IRQ_MBHC_MOISTURE_INT,
	WCD9378_IRQ_HPHL_SURGE_DET_INT,
	WCD9378_IRQ_HPHR_SURGE_DET_INT,
	WCD9378_IRQ_SAPU_PROT_MODE_CHG,
	WCD9378_NUM_IRQS,
};

struct gpio_desc;
struct wcd_mbhc;
struct wcd_clsh_ctrl;

struct wcd9378_priv;
struct wcd9378_sdw_priv {
	struct sdw_slave *sdev;
	struct sdw_stream_config sconfig;
	struct sdw_stream_runtime *sruntime;
	struct sdw_port_config port_config[WCD9378_MAX_SWR_PORTS];
	struct wcd_sdw_ch_info *ch_info;
	bool port_enable[WCD9378_MAX_SWR_CH_IDS];
	unsigned int master_channel_map[SDW_MAX_PORTS];
	int active_ports;
	int num_ports;
	bool is_tx;
	struct wcd9378_priv *wcd9378;
	struct irq_domain *slave_irq;
	struct regmap *regmap;
};

struct wcd9378_priv {
	struct device *rxdev;
	struct device *txdev;
	struct device_node *rxnode;
	struct device_node *txnode;
	struct sdw_slave *tx_sdw_dev;
	struct sdw_slave *rx_sdw_dev;
	struct wcd9378_sdw_priv *sdw_priv[NUM_CODEC_DAIS];
	struct regmap *regmap;
	struct gpio_desc *reset_gpio;
	/* Serialize micbias-related configuration updates. */
	struct mutex micb_lock;
	struct wcd_common common;
	struct wcd_mbhc_config mbhc_cfg;
	struct wcd_mbhc *wcd_mbhc;
	struct wcd_clsh_ctrl *clsh_info;
	bool tx_sdw_attached;
};

#if IS_ENABLED(CONFIG_SND_SOC_WCD9378_SDW)
int wcd9378_sdw_free(struct wcd9378_sdw_priv *wcd,
		     struct snd_pcm_substream *substream,
		     struct snd_soc_dai *dai);
int wcd9378_sdw_set_sdw_stream(struct wcd9378_sdw_priv *wcd,
			       struct snd_soc_dai *dai,
			       void *stream, int direction);
int wcd9378_sdw_hw_params(struct wcd9378_sdw_priv *wcd,
			  struct snd_pcm_substream *substream,
			  struct snd_pcm_hw_params *params,
			  struct snd_soc_dai *dai);
#else
static inline int
wcd9378_sdw_free(struct wcd9378_sdw_priv *wcd,
		 struct snd_pcm_substream *substream,
		 struct snd_soc_dai *dai)
{
	return -EOPNOTSUPP;
}

static inline int
wcd9378_sdw_set_sdw_stream(struct wcd9378_sdw_priv *wcd,
			   struct snd_soc_dai *dai,
			   void *stream, int direction)
{
	return -EOPNOTSUPP;
}

static inline int
wcd9378_sdw_hw_params(struct wcd9378_sdw_priv *wcd,
		      struct snd_pcm_substream *substream,
		      struct snd_pcm_hw_params *params,
		      struct snd_soc_dai *dai)
{
	return -EOPNOTSUPP;
}
#endif

#endif /* _WCD9378_STATIC_PROTOTYPE_H */
