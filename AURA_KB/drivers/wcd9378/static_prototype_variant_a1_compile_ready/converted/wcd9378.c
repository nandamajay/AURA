// SPDX-License-Identifier: GPL-2.0-only
/*
 * Qualcomm WCD9378 codec static RFC prototype.
 */

#include <linux/component.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/gpio/consumer.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_runtime.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/regulator/consumer.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/soundwire/sdw.h>
#include <sound/soc-dapm.h>
#include <sound/soc.h>
#include "wcd-clsh-v2.h"
#include "wcd-common.h"
#include "wcd-mbhc-v2.h"
#include "wcd9378.h"

#define WCD9378_HS_V_MAX_MV 1600

static const char * const wcd9378_supplies[] = {
	"vdd-buck",
	"vdd-rxtx",
	"vdd-px",
	"vdd-mic-bias",
};

static int wcd9378_check_tx_capture_ready(struct wcd9378_priv *wcd9378,
					  struct snd_soc_dai *dai,
					  const char *op)
{
	if (dai->id != AIF1_CAP)
		return 0;

	if (wcd9378->tx_slave_ready)
		return 0;

	dev_warn(dai->dev,
		 "Rejecting TX capture %s: TX SoundWire slave is UNATTACHED\n",
		 op);

	return -ENODEV;
}

static const char * const wcd9378_rx_hph_mode_text[] = {
	"CLS_H_INVALID", "CLS_H_HIFI", "CLS_H_LP", "CLS_AB", "CLS_H_LOHIFI",
	"CLS_H_ULP", "CLS_AB_HIFI", "CLS_AB_LP", "CLS_AB_LOHIFI",
};

static const struct soc_enum wcd9378_hph_mode_enum =
	SOC_ENUM_SINGLE_EXT(ARRAY_SIZE(wcd9378_rx_hph_mode_text),
			    wcd9378_rx_hph_mode_text);

static void wcd9378_dump_hph_state(struct snd_soc_component *component)
{
	unsigned int val;

	val = snd_soc_component_read(component, WCD9378_ANA_HPH);
	dev_info(component->dev, "HPH_STATE: ANA_HPH=0x%02x\n", val & 0xff);

	val = snd_soc_component_read(component, WCD9378_CDC_HPH_GAIN_CTL);
	dev_info(component->dev, "HPH_STATE: CDC_HPH_GAIN_CTL=0x%02x\n",
		 val & 0xff);

	val = snd_soc_component_read(component, WCD9378_HPH_RDAC_CLK_CTL1);
	dev_info(component->dev, "HPH_STATE: HPH_RDAC_CLK_CTL1=0x%02x\n",
		 val & 0xff);

	val = snd_soc_component_read(component, WCD9378_CDC_COMP_CTL_0);
	dev_info(component->dev, "HPH_STATE: CDC_COMP_CTL_0=0x%02x\n",
		 val & 0xff);
}

static int wcd9378_get_compander(struct snd_kcontrol *kcontrol,
				 struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	if (strstr(kcontrol->id.name, "HPHL"))
		ucontrol->value.integer.value[0] = wcd9378->comp1_enable;
	else
		ucontrol->value.integer.value[0] = wcd9378->comp2_enable;

	return 0;
}

static int wcd9378_set_compander(struct snd_kcontrol *kcontrol,
				 struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);
	bool enable = !!ucontrol->value.integer.value[0];

	if (strstr(kcontrol->id.name, "HPHL"))
		wcd9378->comp1_enable = enable;
	else
		wcd9378->comp2_enable = enable;

	return 0;
}

static int wcd9378_rx_hph_mode_get(struct snd_kcontrol *kcontrol,
				   struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	ucontrol->value.enumerated.item[0] = wcd9378->hph_mode;
	return 0;
}

static int wcd9378_rx_hph_mode_put(struct snd_kcontrol *kcontrol,
				   struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);
	unsigned int mode = ucontrol->value.enumerated.item[0];

	if (mode >= ARRAY_SIZE(wcd9378_rx_hph_mode_text))
		return -EINVAL;

	wcd9378->hph_mode = mode;
	return 0;
}

static int wcd9378_hph_gain_get(struct snd_kcontrol *kcontrol,
				struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	if (strstr(kcontrol->id.name, "HPHL"))
		ucontrol->value.integer.value[0] = wcd9378->hphl_gain;
	else
		ucontrol->value.integer.value[0] = wcd9378->hphr_gain;

	return 0;
}

static int wcd9378_hph_gain_put(struct snd_kcontrol *kcontrol,
				struct snd_ctl_elem_value *ucontrol)
{
	struct snd_soc_component *component = snd_kcontrol_chip(kcontrol);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);
	unsigned int gain = ucontrol->value.integer.value[0];

	if (gain > WCD9378_HPH_GAIN_MAX)
		return -EINVAL;

	if (strstr(kcontrol->id.name, "HPHL"))
		wcd9378->hphl_gain = gain;
	else
		wcd9378->hphr_gain = gain;

	return 0;
}

static int wcd9378_hphl_pga_event(struct snd_soc_dapm_widget *w,
				  struct snd_kcontrol *kcontrol,
				  int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);

	dev_info(component->dev, "HPHL PGA: event=%d\n", event);
	return 0;
}

static int wcd9378_hphr_pga_event(struct snd_soc_dapm_widget *w,
				  struct snd_kcontrol *kcontrol,
				  int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);

	dev_info(component->dev, "HPHR PGA: event=%d\n", event);
	return 0;
}

static int wcd9378_hphl_pa_event(struct snd_soc_dapm_widget *w,
				 struct snd_kcontrol *kcontrol,
				 int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	switch (event) {
	case SND_SOC_DAPM_PRE_PMU:
		dev_info(component->dev, "HPHL PA: PRE_PMU hph_mode=%d\n",
			 wcd9378->hph_mode);
		wcd9378_dump_hph_state(component);
		break;
	case SND_SOC_DAPM_POST_PMU:
		dev_info(component->dev, "HPHL PA: POST_PMU enabled\n");
		break;
	case SND_SOC_DAPM_POST_PMD:
		dev_info(component->dev, "HPHL PA: POST_PMD disabled\n");
		break;
	}

	return 0;
}

static int wcd9378_hphr_pa_event(struct snd_soc_dapm_widget *w,
				 struct snd_kcontrol *kcontrol,
				 int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	switch (event) {
	case SND_SOC_DAPM_PRE_PMU:
		dev_info(component->dev, "HPHR PA: PRE_PMU hph_mode=%d\n",
			 wcd9378->hph_mode);
		break;
	case SND_SOC_DAPM_POST_PMU:
		dev_info(component->dev, "HPHR PA: POST_PMU enabled\n");
		break;
	case SND_SOC_DAPM_POST_PMD:
		dev_info(component->dev, "HPHR PA: POST_PMD disabled\n");
		break;
	}

	return 0;
}

static int wcd9378_clsh_pa_event(struct snd_soc_dapm_widget *w,
				 struct snd_kcontrol *kcontrol,
				 int event)
{
	struct snd_soc_component *component = snd_soc_dapm_to_component(w->dapm);
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	dev_info(component->dev, "CLSH PA: event=%d hph_mode=%d\n",
		 event, wcd9378->hph_mode);

	switch (event) {
	case SND_SOC_DAPM_PRE_PMU:
		wcd9378->clsh_pa_enabled = true;
		break;
	case SND_SOC_DAPM_POST_PMD:
		wcd9378->clsh_pa_enabled = false;
		break;
	}

	return 0;
}

static int wcd9378_codec_hw_params(struct snd_pcm_substream *substream,
				   struct snd_pcm_hw_params *params,
				   struct snd_soc_dai *dai)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dai->dev);
	struct wcd9378_sdw_priv *wcd = wcd9378->sdw_priv[dai->id];
	int ret;

	if (!wcd)
		return -EINVAL;

	ret = wcd9378_check_tx_capture_ready(wcd9378, dai, "hw_params");
	if (ret)
		return ret;

	return wcd9378_sdw_hw_params(wcd, substream, params, dai);
}

static int wcd9378_codec_free(struct snd_pcm_substream *substream,
			      struct snd_soc_dai *dai)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dai->dev);
	struct wcd9378_sdw_priv *wcd = wcd9378->sdw_priv[dai->id];

	if (!wcd)
		return -EINVAL;

	return wcd9378_sdw_free(wcd, substream, dai);
}

static int wcd9378_codec_set_sdw_stream(struct snd_soc_dai *dai,
					void *stream, int direction)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dai->dev);
	struct wcd9378_sdw_priv *wcd = wcd9378->sdw_priv[dai->id];
	int ret;

	if (!wcd)
		return -EINVAL;

	ret = wcd9378_check_tx_capture_ready(wcd9378, dai, "set_stream");
	if (ret)
		return ret;

	return wcd9378_sdw_set_sdw_stream(wcd, dai, stream, direction);
}

static void wcd9378_init_default_sdw_port_config(struct wcd9378_priv *wcd9378)
{
	struct wcd9378_sdw_priv *rx = wcd9378->sdw_priv[AIF1_PB];
	struct wcd9378_sdw_priv *tx = wcd9378->sdw_priv[AIF1_CAP];

	/* Default playback: route stereo stream via RX HPH slave port 1. */
	if (rx) {
		rx->port_config[WCD9378_HPH_PORT - 1].num = WCD9378_HPH_PORT;
		rx->port_config[WCD9378_HPH_PORT - 1].ch_mask = BIT(0) | BIT(1);
		rx->master_channel_map[WCD9378_HPH_PORT - 1] = BIT(0) | BIT(1);
	}

	/* Default capture placeholder: ADC1 on TX port 1 (blocked if TX unattached). */
	if (tx) {
		tx->port_config[WCD9378_ADC_1_PORT - 1].num = WCD9378_ADC_1_PORT;
		tx->port_config[WCD9378_ADC_1_PORT - 1].ch_mask = BIT(0);
		tx->master_channel_map[WCD9378_ADC_1_PORT - 1] = BIT(0);
	}
}

static int wcd9378_get_channel_map(const struct snd_soc_dai *dai,
				   unsigned int *tx_num,
				   unsigned int *tx_slot,
				   unsigned int *rx_num,
				   unsigned int *rx_slot)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dai->dev);
	struct wcd9378_sdw_priv *wcd = wcd9378->sdw_priv[dai->id];
	int i;

	if (!wcd)
		return -EINVAL;

	switch (dai->id) {
	case AIF1_PB:
		if (!rx_slot || !rx_num)
			return -EINVAL;
		for (i = 0; i < SDW_MAX_PORTS; i++)
			rx_slot[i] = wcd->master_channel_map[i];
		*rx_num = i;
		break;
	case AIF1_CAP:
		if (!tx_slot || !tx_num)
			return -EINVAL;
		for (i = 0; i < SDW_MAX_PORTS; i++)
			tx_slot[i] = wcd->master_channel_map[i];
		*tx_num = i;
		break;
	default:
		return -EINVAL;
	}

	return 0;
}

static const struct snd_soc_dai_ops wcd9378_sdw_dai_ops = {
	.hw_params = wcd9378_codec_hw_params,
	.hw_free = wcd9378_codec_free,
	.set_stream = wcd9378_codec_set_sdw_stream,
	.get_channel_map = wcd9378_get_channel_map,
};

static struct snd_soc_dai_driver wcd9378_dais[] = {
	[0] = {
		.name = "wcd9378-sdw-rx",
		.playback = {
			.stream_name = "WCD9378 AIF Playback",
			.rates = WCD9378_RATES | WCD9378_FRAC_RATES,
			.formats = WCD9378_FORMATS,
			.rate_min = 8000,
			.rate_max = 384000,
			.channels_min = 1,
			.channels_max = 4,
		},
		.ops = &wcd9378_sdw_dai_ops,
	},
	[1] = {
		.name = "wcd9378-sdw-tx",
		.capture = {
			.stream_name = "WCD9378 AIF Capture",
			.rates = WCD9378_RATES,
			.formats = WCD9378_FORMATS,
			.rate_min = 8000,
			.rate_max = 192000,
			.channels_min = 1,
			.channels_max = 4,
		},
		.ops = &wcd9378_sdw_dai_ops,
	},
};

static void wcd9378_reset(struct wcd9378_priv *wcd9378)
{
	if (wcd9378->common.dev)
		dev_info(wcd9378->common.dev, "Applying WCD9378 reset toggle\n");

	gpiod_set_value(wcd9378->reset_gpio, 1);
	usleep_range(20, 30);
	gpiod_set_value(wcd9378->reset_gpio, 0);
	usleep_range(20, 30);

	if (wcd9378->common.dev)
		dev_info(wcd9378->common.dev, "WCD9378 reset toggle complete\n");
}

static int wcd9378_soc_codec_probe(struct snd_soc_component *component)
{
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);
	struct sdw_slave *tx_sdw_dev = wcd9378->tx_sdw_dev;
	struct device *dev = component->dev;
	struct device *tx_swr_dev;
	bool tx_attached = true;
	unsigned long time_left;
	int ret;

	if (!tx_sdw_dev)
		return -EINVAL;

	tx_swr_dev = tx_sdw_dev->bus->dev;
	if (!tx_swr_dev)
		return -EINVAL;

	/*
	 * Mark TX unavailable until SoundWire attach+init has been observed in
	 * this probe instance.
	 */
	wcd9378->tx_slave_ready = false;

	/*
	 * Keep codec and TX SoundWire master runtime-active while waiting for
	 * TX slave attach/initialization completions.
	 */
	ret = pm_runtime_resume_and_get(dev);
	if (ret < 0)
		return ret;

	ret = pm_runtime_resume_and_get(tx_swr_dev);
	if (ret < 0)
		goto err_put_codec_pm;

	/* Wait for TX slave to re-attach before initialization completion. */
	time_left = wait_for_completion_timeout(&tx_sdw_dev->enumeration_complete,
						msecs_to_jiffies(WCD9378_SDW_INIT_TIMEOUT_MS));
	if (!time_left) {
		dev_err(dev, "TX SoundWire slave enumeration timed out, status: %d\n",
			tx_sdw_dev->status);

		if (tx_sdw_dev->status == SDW_SLAVE_UNATTACHED) {
			tx_attached = false;
			dev_warn(dev,
				 "TX SoundWire slave still UNATTACHED after enumeration wait\n");
			dev_warn(dev,
				 "Continuing probe in degraded mode; capture remains unavailable until TX SoundWire attach issue is fixed\n");
		} else {
			ret = -ETIMEDOUT;
			goto err_put_tx_swr_pm;
		}
	}

	if (tx_attached) {
		time_left = wait_for_completion_timeout(&tx_sdw_dev->initialization_complete,
							msecs_to_jiffies(WCD9378_SDW_INIT_TIMEOUT_MS));
		if (!time_left) {
			dev_err(dev,
				"TX SoundWire slave initialization timed out, status: %d\n",
				tx_sdw_dev->status);
			if (tx_sdw_dev->status == SDW_SLAVE_UNATTACHED) {
				dev_warn(dev,
					 "TX SoundWire slave still UNATTACHED after initialization wait\n");
				dev_warn(dev,
					 "Continuing probe in degraded mode; capture remains unavailable until TX SoundWire attach issue is fixed\n");
				tx_attached = false;
			} else {
				ret = -ETIMEDOUT;
				goto err_put_tx_swr_pm;
			}
		}
	}

	wcd9378->tx_slave_ready = tx_attached;
	dev_info(component->dev, "probe: tx_slave_ready=%d\n",
		 wcd9378->tx_slave_ready);
	dev_info(component->dev, "probe: registering %d DAPM widgets, %d kcontrols\n",
		 component->driver->num_dapm_widgets,
		 component->driver->num_controls);

	snd_soc_component_init_regmap(component, wcd9378->regmap);

	wcd9378->clsh_info = wcd_clsh_ctrl_alloc(component, WCD937X);
	if (IS_ERR(wcd9378->clsh_info)) {
		ret = PTR_ERR(wcd9378->clsh_info);
		wcd9378->clsh_info = NULL;
		goto err_put_tx_swr_pm;
	}

	wcd9378_dump_hph_state(component);

	pm_runtime_put(tx_swr_dev);
	pm_runtime_put(dev);

	return 0;

err_put_tx_swr_pm:
	pm_runtime_put(tx_swr_dev);
err_put_codec_pm:
	pm_runtime_put(dev);
	return ret;
}

static void wcd9378_soc_codec_remove(struct snd_soc_component *component)
{
	struct wcd9378_priv *wcd9378 = snd_soc_component_get_drvdata(component);

	if (wcd9378->wcd_mbhc)
		wcd_mbhc_deinit(wcd9378->wcd_mbhc);

	if (wcd9378->clsh_info)
		wcd_clsh_ctrl_free(wcd9378->clsh_info);
}

static int wcd9378_codec_set_jack(struct snd_soc_component *comp,
				  struct snd_soc_jack *jack,
				  void *data)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(comp->dev);

	if (!wcd9378->wcd_mbhc) {
		dev_warn(comp->dev,
			 "MBHC not initialized; skipping jack setup in degraded prototype mode\n");
		return 0;
	}

	if (jack)
		return wcd_mbhc_start(wcd9378->wcd_mbhc, &wcd9378->mbhc_cfg, jack);

	wcd_mbhc_stop(wcd9378->wcd_mbhc);
	return 0;
}

static const struct snd_kcontrol_new wcd9378_kcontrols[] = {
	SOC_SINGLE_EXT("HPHL_COMP Switch", SND_SOC_NOPM, 0, 1, 0,
		       wcd9378_get_compander, wcd9378_set_compander),
	SOC_SINGLE_EXT("HPHR_COMP Switch", SND_SOC_NOPM, 1, 1, 0,
		       wcd9378_get_compander, wcd9378_set_compander),
	SOC_ENUM_EXT("RX HPH Mode", wcd9378_hph_mode_enum,
		     wcd9378_rx_hph_mode_get, wcd9378_rx_hph_mode_put),
	SOC_SINGLE_EXT("HPHL Volume", SND_SOC_NOPM, 0, WCD9378_HPH_GAIN_MAX, 0,
		       wcd9378_hph_gain_get, wcd9378_hph_gain_put),
	SOC_SINGLE_EXT("HPHR Volume", SND_SOC_NOPM, 1, WCD9378_HPH_GAIN_MAX, 0,
		       wcd9378_hph_gain_get, wcd9378_hph_gain_put),
};

static const struct snd_kcontrol_new hphl_rdac_switch[] = {
	SOC_DAPM_SINGLE("Switch", SND_SOC_NOPM, 0, 1, 0)
};

static const struct snd_kcontrol_new hphr_rdac_switch[] = {
	SOC_DAPM_SINGLE("Switch", SND_SOC_NOPM, 0, 1, 0)
};

static const struct snd_kcontrol_new hphl_switch[] = {
	SOC_DAPM_SINGLE("Switch", SND_SOC_NOPM, 0, 1, 0)
};

static const struct snd_kcontrol_new hphr_switch[] = {
	SOC_DAPM_SINGLE("Switch", SND_SOC_NOPM, 0, 1, 0)
};

static const struct snd_kcontrol_new clsh_pa_switch[] = {
	SOC_DAPM_SINGLE("Switch", SND_SOC_NOPM, 0, 1, 0)
};

/*
 * HPH-enabled DAPM set for static prototype card integration.
 * Includes endpoints used by machine audio-routing plus HPH controls/widgets.
 */
static const struct snd_soc_dapm_widget wcd9378_stub_dapm_widgets[] = {
	SND_SOC_DAPM_INPUT("IN1_HPHL"),
	SND_SOC_DAPM_INPUT("IN2_HPHR"),
	SND_SOC_DAPM_INPUT("IN3_AUX"),
	SND_SOC_DAPM_INPUT("AMIC1"),
	SND_SOC_DAPM_INPUT("AMIC2"),
	SND_SOC_DAPM_INPUT("AMIC3"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT0"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT1"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT2"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT4"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT5"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT6"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT7"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT8"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT9"),
	SND_SOC_DAPM_INPUT("TX SWR_INPUT10"),

	SND_SOC_DAPM_SUPPLY("MIC BIAS1", SND_SOC_NOPM, 0, 0, NULL, 0),
	SND_SOC_DAPM_SUPPLY("MIC BIAS2", SND_SOC_NOPM, 0, 0, NULL, 0),
	SND_SOC_DAPM_SUPPLY("MIC BIAS3", SND_SOC_NOPM, 0, 0, NULL, 0),

	SND_SOC_DAPM_MIXER("HPHL_RDAC", SND_SOC_NOPM, 0, 0,
			   hphl_rdac_switch, ARRAY_SIZE(hphl_rdac_switch)),
	SND_SOC_DAPM_MIXER("HPHR_RDAC", SND_SOC_NOPM, 0, 0,
			   hphr_rdac_switch, ARRAY_SIZE(hphr_rdac_switch)),
	SND_SOC_DAPM_PGA_E("HPHL PGA", SND_SOC_NOPM, 0, 0, NULL, 0,
			   wcd9378_hphl_pga_event,
			   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
	SND_SOC_DAPM_PGA_E("HPHR PGA", SND_SOC_NOPM, 0, 0, NULL, 0,
			   wcd9378_hphr_pga_event,
			   SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
	SND_SOC_DAPM_MIXER_E("CLSH PA", SND_SOC_NOPM, 0, 0,
			     clsh_pa_switch, ARRAY_SIZE(clsh_pa_switch),
			     wcd9378_clsh_pa_event,
			     SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMD),
	SND_SOC_DAPM_OUT_DRV_E("HPHL", SND_SOC_NOPM, 0, 0,
			       hphl_switch, ARRAY_SIZE(hphl_switch),
			       wcd9378_hphl_pa_event,
			       SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMU |
			       SND_SOC_DAPM_PRE_PMD | SND_SOC_DAPM_POST_PMD),
	SND_SOC_DAPM_OUT_DRV_E("HPHR", SND_SOC_NOPM, 0, 0,
			       hphr_switch, ARRAY_SIZE(hphr_switch),
			       wcd9378_hphr_pa_event,
			       SND_SOC_DAPM_PRE_PMU | SND_SOC_DAPM_POST_PMU |
			       SND_SOC_DAPM_PRE_PMD | SND_SOC_DAPM_POST_PMD),

	SND_SOC_DAPM_OUTPUT("HPHL_OUT"),
	SND_SOC_DAPM_OUTPUT("HPHR_OUT"),
	SND_SOC_DAPM_OUTPUT("AUX_OUT"),
	SND_SOC_DAPM_OUTPUT("ADC1_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("ADC2_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("ADC3_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC1_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC2_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC3_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC4_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC5_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC6_OUTPUT"),
	SND_SOC_DAPM_OUTPUT("DMIC7_OUTPUT"),
};

static const struct snd_soc_dapm_route wcd9378_stub_audio_map[] = {
	/* HPH playback routes */
	{ "HPHL_RDAC", "Switch", "IN1_HPHL" },
	{ "HPHL PGA", NULL, "HPHL_RDAC" },
	{ "HPHL", NULL, "HPHL PGA" },
	{ "HPHL", NULL, "CLSH PA" },
	{ "HPHL_OUT", NULL, "HPHL" },

	{ "HPHR_RDAC", "Switch", "IN2_HPHR" },
	{ "HPHR PGA", NULL, "HPHR_RDAC" },
	{ "HPHR", NULL, "HPHR PGA" },
	{ "HPHR", NULL, "CLSH PA" },
	{ "HPHR_OUT", NULL, "HPHR" },

	{ "AUX_OUT", NULL, "IN3_AUX" },

	/* TX/capture endpoint relations used by machine audio-routing */
	{ "ADC1_OUTPUT", NULL, "TX SWR_INPUT0" },
	{ "ADC2_OUTPUT", NULL, "TX SWR_INPUT1" },
	{ "ADC3_OUTPUT", NULL, "TX SWR_INPUT2" },
	{ "DMIC1_OUTPUT", NULL, "TX SWR_INPUT4" },
	{ "DMIC2_OUTPUT", NULL, "TX SWR_INPUT5" },
	{ "DMIC3_OUTPUT", NULL, "TX SWR_INPUT6" },
	{ "DMIC4_OUTPUT", NULL, "TX SWR_INPUT7" },
	{ "DMIC5_OUTPUT", NULL, "TX SWR_INPUT8" },
	{ "DMIC6_OUTPUT", NULL, "TX SWR_INPUT9" },
	{ "DMIC7_OUTPUT", NULL, "TX SWR_INPUT10" },
	{ "AMIC1", NULL, "MIC BIAS1" },
	{ "AMIC2", NULL, "MIC BIAS2" },
	{ "AMIC3", NULL, "MIC BIAS3" },
};

static const struct snd_soc_component_driver soc_codec_dev_wcd9378 = {
	.name = "wcd9378_codec",
	.probe = wcd9378_soc_codec_probe,
	.remove = wcd9378_soc_codec_remove,
	.controls = wcd9378_kcontrols,
	.num_controls = ARRAY_SIZE(wcd9378_kcontrols),
	.dapm_widgets = wcd9378_stub_dapm_widgets,
	.num_dapm_widgets = ARRAY_SIZE(wcd9378_stub_dapm_widgets),
	.dapm_routes = wcd9378_stub_audio_map,
	.num_dapm_routes = ARRAY_SIZE(wcd9378_stub_audio_map),
	.set_jack = wcd9378_codec_set_jack,
	.endianness = 1,
};

static int wcd9378_bind(struct device *dev)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dev);
	int ret;

	usleep_range(5000, 5010);

	ret = component_bind_all(dev, wcd9378);
	if (ret)
		return ret;

	wcd9378->rxdev = of_sdw_find_device_by_node(wcd9378->rxnode);
	if (!wcd9378->rxdev) {
		ret = -EINVAL;
		goto err_component_unbind;
	}

	wcd9378->sdw_priv[AIF1_PB] = dev_get_drvdata(wcd9378->rxdev);
	if (!wcd9378->sdw_priv[AIF1_PB]) {
		ret = -EINVAL;
		goto err_put_rxdev;
	}

	wcd9378->sdw_priv[AIF1_PB]->wcd9378 = wcd9378;
	wcd9378->rx_sdw_dev = dev_to_sdw_dev(wcd9378->rxdev);
	dev_info(dev, "RX SoundWire slave: %s dev_num=%d status=%d\n",
		 dev_name(&wcd9378->rx_sdw_dev->dev),
		 wcd9378->rx_sdw_dev->dev_num,
		 wcd9378->rx_sdw_dev->status);

	wcd9378->txdev = of_sdw_find_device_by_node(wcd9378->txnode);
	if (!wcd9378->txdev) {
		ret = -EINVAL;
		goto err_put_rxdev;
	}

	wcd9378->sdw_priv[AIF1_CAP] = dev_get_drvdata(wcd9378->txdev);
	if (!wcd9378->sdw_priv[AIF1_CAP]) {
		ret = -EINVAL;
		goto err_put_txdev;
	}

	wcd9378->sdw_priv[AIF1_CAP]->wcd9378 = wcd9378;
	wcd9378->tx_sdw_dev = dev_to_sdw_dev(wcd9378->txdev);
	dev_info(dev, "TX SoundWire slave: %s dev_num=%d status=%d\n",
		 dev_name(&wcd9378->tx_sdw_dev->dev),
		 wcd9378->tx_sdw_dev->dev_num,
		 wcd9378->tx_sdw_dev->status);

	wcd9378_init_default_sdw_port_config(wcd9378);
	dev_info(dev, "Initialized default WCD9378 SDW RX/TX port configuration\n");

	if (!device_link_add(wcd9378->rxdev, wcd9378->txdev,
			     DL_FLAG_STATELESS | DL_FLAG_PM_RUNTIME)) {
		ret = -EINVAL;
		goto err_put_txdev;
	}

	if (!device_link_add(dev, wcd9378->txdev,
			     DL_FLAG_STATELESS | DL_FLAG_PM_RUNTIME)) {
		ret = -EINVAL;
		goto err_remove_link1;
	}

	if (!device_link_add(dev, wcd9378->rxdev,
			     DL_FLAG_STATELESS | DL_FLAG_PM_RUNTIME)) {
		ret = -EINVAL;
		goto err_remove_link2;
	}

	wcd9378->regmap = wcd9378->sdw_priv[AIF1_CAP]->regmap;
	if (!wcd9378->regmap) {
		ret = -EINVAL;
		goto err_remove_link3;
	}

	ret = snd_soc_register_component(dev, &soc_codec_dev_wcd9378,
					 wcd9378_dais,
					 ARRAY_SIZE(wcd9378_dais));
	if (ret)
		goto err_remove_link3;

	return 0;

err_remove_link3:
	device_link_remove(dev, wcd9378->rxdev);
err_remove_link2:
	device_link_remove(dev, wcd9378->txdev);
err_remove_link1:
	device_link_remove(wcd9378->rxdev, wcd9378->txdev);
err_put_txdev:
	put_device(wcd9378->txdev);
err_put_rxdev:
	put_device(wcd9378->rxdev);
err_component_unbind:
	component_unbind_all(dev, wcd9378);
	return ret;
}

static void wcd9378_unbind(struct device *dev)
{
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dev);

	snd_soc_unregister_component(dev);
	device_link_remove(dev, wcd9378->txdev);
	device_link_remove(dev, wcd9378->rxdev);
	device_link_remove(wcd9378->rxdev, wcd9378->txdev);
	component_unbind_all(dev, wcd9378);
	put_device(wcd9378->txdev);
	put_device(wcd9378->rxdev);
}

static const struct component_master_ops wcd9378_comp_ops = {
	.bind = wcd9378_bind,
	.unbind = wcd9378_unbind,
};

static int wcd9378_add_slave_components(struct wcd9378_priv *wcd9378,
					struct device *dev,
					struct component_match **matchptr)
{
	struct device_node *np = dev->of_node;

	wcd9378->rxnode = of_parse_phandle(np, "qcom,rx-device", 0);
	if (!wcd9378->rxnode)
		return -ENODEV;

	component_match_add_release(dev, matchptr, component_release_of,
				    component_compare_of, wcd9378->rxnode);

	wcd9378->txnode = of_parse_phandle(np, "qcom,tx-device", 0);
	if (!wcd9378->txnode)
		return -ENODEV;

	component_match_add_release(dev, matchptr, component_release_of,
				    component_compare_of, wcd9378->txnode);

	return 0;
}

static int wcd9378_probe(struct platform_device *pdev)
{
	struct component_match *match = NULL;
	struct device *dev = &pdev->dev;
	struct wcd9378_priv *wcd9378;
	int ret;

	wcd9378 = devm_kzalloc(dev, sizeof(*wcd9378), GFP_KERNEL);
	if (!wcd9378)
		return -ENOMEM;

	dev_set_drvdata(dev, wcd9378);

	mutex_init(&wcd9378->micb_lock);
	wcd9378->common.dev = dev;
	wcd9378->common.max_bias = WCD9378_MAX_MICBIAS;

	ret = devm_regulator_bulk_get_enable(dev, ARRAY_SIZE(wcd9378_supplies),
					     wcd9378_supplies);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to get and enable supplies\n");

	wcd9378->reset_gpio = devm_gpiod_get(dev, "reset", GPIOD_OUT_LOW);
	if (IS_ERR(wcd9378->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(wcd9378->reset_gpio),
				     "failed to request reset gpio\n");

	ret = wcd_dt_parse_micbias_info(&wcd9378->common);
	if (ret)
		return dev_err_probe(dev, ret, "Failed to parse micbias properties\n");

	wcd9378->mbhc_cfg.mbhc_micbias = MIC_BIAS_2;
	wcd9378->mbhc_cfg.anc_micbias = MIC_BIAS_2;
	wcd9378->mbhc_cfg.v_hs_max = WCD9378_HS_V_MAX_MV;
	wcd9378->mbhc_cfg.num_btn = WCD_MBHC_DEF_BUTTONS;
	wcd9378->mbhc_cfg.micb_mv = wcd9378->common.micb_mv[1];
	wcd9378->mbhc_cfg.linein_th = 5000;
	wcd9378->mbhc_cfg.hs_thr = 1700;
	wcd9378->mbhc_cfg.hph_thr = 50;

	wcd_dt_parse_mbhc_data(dev, &wcd9378->mbhc_cfg);

	ret = wcd9378_add_slave_components(wcd9378, dev, &match);
	if (ret)
		return ret;

	wcd9378_reset(wcd9378);

	ret = component_master_add_with_match(dev, &wcd9378_comp_ops, match);
	if (ret)
		return ret;

	pm_runtime_set_autosuspend_delay(dev, 1000);
	pm_runtime_use_autosuspend(dev);
	pm_runtime_mark_last_busy(dev);
	pm_runtime_set_active(dev);
	pm_runtime_enable(dev);
	pm_runtime_idle(dev);

	return 0;
}

static void wcd9378_remove(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct wcd9378_priv *wcd9378 = dev_get_drvdata(dev);

	component_master_del(dev, &wcd9378_comp_ops);

	pm_runtime_disable(dev);
	pm_runtime_set_suspended(dev);
	pm_runtime_dont_use_autosuspend(dev);
	mutex_destroy(&wcd9378->micb_lock);
}

#if defined(CONFIG_OF)
static const struct of_device_id wcd9378_of_match[] = {
	{ .compatible = "qcom,wcd9378-codec" },
	{ }
};
MODULE_DEVICE_TABLE(of, wcd9378_of_match);
#endif

static struct platform_driver wcd9378_codec_driver = {
	.probe = wcd9378_probe,
	.remove = wcd9378_remove,
	.driver = {
		.name = WCD9378_DRV_NAME,
		.of_match_table = of_match_ptr(wcd9378_of_match),
		.suppress_bind_attrs = true,
	},
};

module_platform_driver(wcd9378_codec_driver);

MODULE_DESCRIPTION("WCD9378 codec static prototype driver");
MODULE_LICENSE("GPL");
