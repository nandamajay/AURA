// SPDX-License-Identifier: GPL-2.0-only
/*
 * Qualcomm WCD9378 SoundWire static RFC prototype.
 */

#include <linux/component.h>
#include <linux/device.h>
#include <linux/irq.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/pm_runtime.h>
#include <linux/regmap.h>
#include <linux/slab.h>
#include <linux/soundwire/sdw.h>
#include <linux/soundwire/sdw_registers.h>
#include <linux/soundwire/sdw_type.h>
#include <sound/soc.h>
#include "wcd-common.h"
#include "wcd9378.h"

static const struct wcd_sdw_ch_info wcd9378_sdw_rx_ch_info[] = {
	WCD_SDW_CH(WCD9378_HPH_L, WCD9378_HPH_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_HPH_R, WCD9378_HPH_PORT, BIT(1)),
	WCD_SDW_CH(WCD9378_CLSH, WCD9378_CLSH_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_COMP_L, WCD9378_COMP_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_COMP_R, WCD9378_COMP_PORT, BIT(1)),
	WCD_SDW_CH(WCD9378_LO, WCD9378_LO_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_DSD_L, WCD9378_DSD_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_DSD_R, WCD9378_DSD_PORT, BIT(1)),
};

static const struct wcd_sdw_ch_info wcd9378_sdw_tx_ch_info[] = {
	WCD_SDW_CH(WCD9378_ADC1, WCD9378_ADC_1_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_ADC2, WCD9378_ADC_2_3_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_ADC3, WCD9378_ADC_2_3_PORT, BIT(1)),
	WCD_SDW_CH(WCD9378_ADC4, WCD9378_ADC_2_3_PORT, BIT(2)),
	WCD_SDW_CH(WCD9378_DMIC0, WCD9378_DMIC_0_3_MBHC_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_DMIC1, WCD9378_DMIC_0_3_MBHC_PORT, BIT(1)),
	WCD_SDW_CH(WCD9378_MBHC, WCD9378_DMIC_0_3_MBHC_PORT, BIT(2)),
	WCD_SDW_CH(WCD9378_DMIC2, WCD9378_DMIC_0_3_MBHC_PORT, BIT(2)),
	WCD_SDW_CH(WCD9378_DMIC3, WCD9378_DMIC_0_3_MBHC_PORT, BIT(3)),
	WCD_SDW_CH(WCD9378_DMIC4, WCD9378_DMIC_4_7_PORT, BIT(0)),
	WCD_SDW_CH(WCD9378_DMIC5, WCD9378_DMIC_4_7_PORT, BIT(1)),
	WCD_SDW_CH(WCD9378_DMIC6, WCD9378_DMIC_4_7_PORT, BIT(2)),
	WCD_SDW_CH(WCD9378_DMIC7, WCD9378_DMIC_4_7_PORT, BIT(3)),
};

static struct sdw_dpn_prop wcd9378_rx_dpn_prop[WCD9378_MAX_SWR_PORTS] = {
	{
		.num = WCD9378_HPH_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_CLSH_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 1,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_COMP_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_LO_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 1,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_DSD_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
};

static struct sdw_dpn_prop wcd9378_tx_dpn_prop[WCD9378_MAX_TX_SWR_PORTS] = {
	{
		.num = WCD9378_ADC_1_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 1,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_ADC_2_3_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 3,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_DMIC_0_3_MBHC_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 4,
		.simple_ch_prep_sm = true,
	}, {
		.num = WCD9378_DMIC_4_7_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 4,
		.simple_ch_prep_sm = true,
	},
};

int wcd9378_sdw_hw_params(struct wcd9378_sdw_priv *wcd,
			  struct snd_pcm_substream *substream,
			  struct snd_pcm_hw_params *params,
			  struct snd_soc_dai *dai)
{
	struct sdw_port_config port_config[WCD9378_MAX_SWR_PORTS];
	unsigned long ch_mask;
	int i, j;

	wcd->sconfig.ch_count = 1;
	wcd->active_ports = 0;
	for (i = 0; i < WCD9378_MAX_SWR_PORTS; i++) {
		ch_mask = wcd->port_config[i].ch_mask;
		if (!ch_mask)
			continue;

		for_each_set_bit(j, &ch_mask, 4)
			wcd->sconfig.ch_count++;

		port_config[wcd->active_ports] = wcd->port_config[i];
		wcd->active_ports++;
	}

	wcd->sconfig.bps = 1;
	wcd->sconfig.frame_rate = params_rate(params);
	wcd->sconfig.direction = wcd->is_tx ? SDW_DATA_DIR_TX : SDW_DATA_DIR_RX;
	wcd->sconfig.type = SDW_STREAM_PCM;

	return sdw_stream_add_slave(wcd->sdev, &wcd->sconfig,
				    &port_config[0], wcd->active_ports,
				    wcd->sruntime);
}
EXPORT_SYMBOL_GPL(wcd9378_sdw_hw_params);

int wcd9378_sdw_free(struct wcd9378_sdw_priv *wcd,
		     struct snd_pcm_substream *substream,
		     struct snd_soc_dai *dai)
{
	sdw_stream_remove_slave(wcd->sdev, wcd->sruntime);

	return 0;
}
EXPORT_SYMBOL_GPL(wcd9378_sdw_free);

int wcd9378_sdw_set_sdw_stream(struct wcd9378_sdw_priv *wcd,
			       struct snd_soc_dai *dai,
			       void *stream, int direction)
{
	wcd->sruntime = stream;

	return 0;
}
EXPORT_SYMBOL_GPL(wcd9378_sdw_set_sdw_stream);

static int wcd9378_interrupt_callback(struct sdw_slave *slave,
				      struct sdw_slave_intr_status *status)
{
	struct wcd9378_sdw_priv *wcd = dev_get_drvdata(&slave->dev);

	return wcd_interrupt_callback(slave, wcd->slave_irq,
			      WCD9378_DIGITAL_INTR_STATUS_0,
			      WCD9378_DIGITAL_INTR_STATUS_1,
			      WCD9378_DIGITAL_INTR_STATUS_2);
}

static bool wcd9378_rdwr_register(struct device *dev, unsigned int reg)
{
	if (reg <= WCD9378_BASE_ADDRESS)
		return false;

	return reg <= WCD9378_MAX_REGISTER;
}

static bool wcd9378_readable_register(struct device *dev, unsigned int reg)
{
	return wcd9378_rdwr_register(dev, reg);
}

static bool wcd9378_writeable_register(struct device *dev, unsigned int reg)
{
	return wcd9378_rdwr_register(dev, reg);
}

static bool wcd9378_volatile_register(struct device *dev, unsigned int reg)
{
	switch (reg) {
	case WCD9378_ANA_MBHC_RESULT_1:
	case WCD9378_ANA_MBHC_RESULT_2:
	case WCD9378_ANA_MBHC_RESULT_3:
	case WCD9378_MBHC_MOISTURE_DET_FSM_STATUS:
	case WCD9378_TX_1_2_SAR1_ERR:
	case WCD9378_TX_1_2_SAR2_ERR:
	case WCD9378_HPH_L_STATUS:
	case WCD9378_HPH_R_STATUS:
	case WCD9378_HPH_SURGE_HPHLR_SURGE_STATUS:
	case WCD9378_EAR_STATUS_REG_1:
	case WCD9378_EAR_STATUS_REG_2:
	case WCD9378_MBHC_NEW_FSM_STATUS:
	case WCD9378_MBHC_NEW_ADC_RESULT:
	case WCD9378_DIE_CRACK_DIE_CRK_DET_OUT:
	case WCD9378_DIGITAL_INTR_STATUS_0:
	case WCD9378_DIGITAL_INTR_STATUS_1:
	case WCD9378_DIGITAL_INTR_STATUS_2:
		return true;
	}

	return false;
}

static const struct regmap_config wcd9378_regmap_config = {
	.name = "wcd9378_sdw",
	.reg_bits = 32,
	.val_bits = 8,
	.cache_type = REGCACHE_MAPLE,
	.max_register = WCD9378_MAX_REGISTER,
	.readable_reg = wcd9378_readable_register,
	.writeable_reg = wcd9378_writeable_register,
	.volatile_reg = wcd9378_volatile_register,
};

static void wcd9378_parse_channel_mapping(struct device *dev,
					  const char *property,
					  u8 *channel_map,
					  size_t channel_map_size)
{
	int count;

	count = of_property_count_u8_elems(dev->of_node, property);
	if (count < 0)
		return;

	if (count > channel_map_size)
		count = channel_map_size;

	of_property_read_u8_array(dev->of_node, property, channel_map, count);
}

static const struct sdw_slave_ops wcd9378_slave_ops = {
	.update_status = wcd_update_status,
	.interrupt_callback = wcd9378_interrupt_callback,
	.bus_config = wcd_bus_config,
};

static int wcd9378_sdw_probe(struct sdw_slave *pdev,
			     const struct sdw_device_id *id)
{
	struct device *dev = &pdev->dev;
	struct wcd9378_sdw_priv *wcd;
	u8 tx_channel_map[WCD9378_MAX_TX_CHANNELS] = { 0 };
	u8 rx_channel_map[WCD9378_MAX_RX_CHANNELS] = { 0 };
	int ret;

	wcd = devm_kzalloc(dev, sizeof(*wcd), GFP_KERNEL);
	if (!wcd)
		return -ENOMEM;

	if (of_property_present(dev->of_node, "qcom,tx-port-mapping")) {
		wcd->is_tx = true;
		ret = of_property_read_u32_array(dev->of_node, "qcom,tx-port-mapping",
						 &pdev->m_port_map[1],
						 WCD9378_MAX_TX_SWR_PORTS);
		wcd9378_parse_channel_mapping(dev, "qcom,tx-channel-mapping",
					      tx_channel_map,
					      ARRAY_SIZE(tx_channel_map));
	} else {
		ret = of_property_read_u32_array(dev->of_node, "qcom,rx-port-mapping",
						 &pdev->m_port_map[1],
						 WCD9378_MAX_SWR_PORTS);
		wcd9378_parse_channel_mapping(dev, "qcom,rx-channel-mapping",
					      rx_channel_map,
					      ARRAY_SIZE(rx_channel_map));
	}

	if (ret < 0)
		dev_info(dev, "Static port mapping not specified\n");

	wcd->sdev = pdev;
	dev_set_drvdata(dev, wcd);

	pdev->prop.scp_int1_mask = SDW_SCP_INT1_IMPL_DEF |
				   SDW_SCP_INT1_BUS_CLASH |
				   SDW_SCP_INT1_PARITY;
	pdev->prop.lane_control_support = true;
	pdev->prop.simple_clk_stop_capable = true;
	pdev->prop.paging_support = true;

	if (wcd->is_tx) {
		pdev->prop.source_ports = GENMASK(WCD9378_MAX_TX_SWR_PORTS - 1, 0);
		pdev->prop.src_dpn_prop = wcd9378_tx_dpn_prop;
		pdev->prop.wake_capable = true;
		wcd->ch_info = (struct wcd_sdw_ch_info *)&wcd9378_sdw_tx_ch_info[0];

		wcd->regmap = devm_regmap_init_sdw(pdev, &wcd9378_regmap_config);
		if (IS_ERR(wcd->regmap))
			return dev_err_probe(dev, PTR_ERR(wcd->regmap),
					     "Regmap init failed\n");

		regcache_cache_only(wcd->regmap, true);
	} else {
		pdev->prop.sink_ports = GENMASK(WCD9378_MAX_SWR_PORTS - 1, 0);
		pdev->prop.sink_dpn_prop = wcd9378_rx_dpn_prop;
		wcd->ch_info = (struct wcd_sdw_ch_info *)&wcd9378_sdw_rx_ch_info[0];
	}

	ret = component_add(dev, &wcd_sdw_component_ops);
	if (ret)
		return ret;

	pm_runtime_set_suspended(dev);

	return 0;
}

static void wcd9378_sdw_remove(struct sdw_slave *pdev)
{
	component_del(&pdev->dev, &wcd_sdw_component_ops);
}

static int wcd9378_sdw_runtime_suspend(struct device *dev)
{
	struct wcd9378_sdw_priv *wcd = dev_get_drvdata(dev);

	if (wcd && wcd->regmap) {
		regcache_cache_only(wcd->regmap, true);
		regcache_mark_dirty(wcd->regmap);
	}

	return 0;
}

static int wcd9378_sdw_runtime_resume(struct device *dev)
{
	struct wcd9378_sdw_priv *wcd = dev_get_drvdata(dev);

	if (wcd && wcd->regmap) {
		regcache_cache_only(wcd->regmap, false);
		regcache_sync(wcd->regmap);
	}

	pm_runtime_mark_last_busy(dev);

	return 0;
}

static const struct sdw_device_id wcd9378_sdw_id[] = {
	SDW_SLAVE_ENTRY(0x0217, WCD9378_CANDIDATE_SDW_PART_ID, 0),
	{},
};
MODULE_DEVICE_TABLE(sdw, wcd9378_sdw_id);

static const struct dev_pm_ops wcd9378_sdw_pm_ops = {
	RUNTIME_PM_OPS(wcd9378_sdw_runtime_suspend,
		       wcd9378_sdw_runtime_resume,
		       NULL)
};

static struct sdw_driver wcd9378_codec_driver = {
	.probe = wcd9378_sdw_probe,
	.remove = wcd9378_sdw_remove,
	.ops = &wcd9378_slave_ops,
	.id_table = wcd9378_sdw_id,
	.driver = {
		.name = "wcd9378-codec",
		.pm = pm_ptr(&wcd9378_sdw_pm_ops),
	},
};
module_sdw_driver(wcd9378_codec_driver);

MODULE_DESCRIPTION("WCD9378 SDW codec static prototype driver");
MODULE_LICENSE("GPL");
