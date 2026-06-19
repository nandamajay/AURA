// SPDX-License-Identifier: GPL-2.0-only
/*
 * Variant-C (combined learnings): deterministic SDW implementation that
 * preserves downstream hardware lineage while adopting upstream SDW lifecycle
 * and API patterns from allowed WCD938x/WCD939x references.
 */

#include <linux/module.h>
#include <linux/slab.h>
#include <linux/platform_device.h>
#include <linux/device.h>
#include <linux/kernel.h>
#include <linux/component.h>
#include <linux/pm_runtime.h>
#include <linux/irq.h>
#include <linux/irqdomain.h>
#include <linux/of.h>
#include <linux/soundwire/sdw.h>
#include <linux/soundwire/sdw_type.h>
#include <linux/soundwire/sdw_registers.h>
#include <linux/regmap.h>
#include <sound/soc.h>
#include <sound/soc-dapm.h>
#include "wcd937x.h"
#include "wcd-common.h"

static const struct wcd_sdw_ch_info wcd937x_sdw_rx_ch_info[] = {
	WCD_SDW_CH(WCD937X_HPH_L, WCD937X_HPH_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_HPH_R, WCD937X_HPH_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_CLSH, WCD937X_CLSH_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_COMP_L, WCD937X_COMP_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_COMP_R, WCD937X_COMP_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_LO, WCD937X_LO_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_DSD_L, WCD937X_DSD_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_DSD_R, WCD937X_DSD_PORT, BIT(1)),
};

static const struct wcd_sdw_ch_info wcd937x_sdw_tx_ch_info[] = {
	WCD_SDW_CH(WCD937X_ADC1, WCD937X_ADC_1_2_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_ADC2, WCD937X_ADC_1_2_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_ADC3, WCD937X_ADC_3_4_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_ADC4, WCD937X_ADC_3_4_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_DMIC0, WCD937X_DMIC_0_3_MBHC_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_DMIC1, WCD937X_DMIC_0_3_MBHC_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_MBHC, WCD937X_DMIC_0_3_MBHC_PORT, BIT(2)),
	WCD_SDW_CH(WCD937X_DMIC2, WCD937X_DMIC_0_3_MBHC_PORT, BIT(2)),
	WCD_SDW_CH(WCD937X_DMIC3, WCD937X_DMIC_0_3_MBHC_PORT, BIT(3)),
	WCD_SDW_CH(WCD937X_DMIC4, WCD937X_DMIC_4_7_PORT, BIT(0)),
	WCD_SDW_CH(WCD937X_DMIC5, WCD937X_DMIC_4_7_PORT, BIT(1)),
	WCD_SDW_CH(WCD937X_DMIC6, WCD937X_DMIC_4_7_PORT, BIT(2)),
	WCD_SDW_CH(WCD937X_DMIC7, WCD937X_DMIC_4_7_PORT, BIT(3)),
};

static struct sdw_dpn_prop wcd937x_rx_dpn_prop[WCD937X_MAX_SWR_PORTS] = {
	{
		.num = WCD937X_HPH_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_CLSH_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 1,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_COMP_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_LO_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 1,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_DSD_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
};

static struct sdw_dpn_prop wcd937x_tx_dpn_prop[WCD937X_MAX_TX_SWR_PORTS] = {
	{
		.num = WCD937X_ADC_1_2_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_ADC_3_4_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 2,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_DMIC_0_3_MBHC_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 4,
		.simple_ch_prep_sm = true,
	},
	{
		.num = WCD937X_DMIC_4_7_PORT,
		.type = SDW_DPN_SIMPLE,
		.min_ch = 1,
		.max_ch = 4,
		.simple_ch_prep_sm = true,
	},
};

int wcd937x_sdw_hw_params(struct wcd937x_sdw_priv *wcd,
			  struct snd_pcm_substream *substream,
			  struct snd_pcm_hw_params *params,
			  struct snd_soc_dai *dai)
{
	struct sdw_port_config port_config[WCD937X_MAX_SWR_PORTS];
	unsigned long ch_mask;
	int i, j;

	wcd->sconfig.ch_count = 1;
	wcd->active_ports = 0;
	for (i = 0; i < WCD937X_MAX_SWR_PORTS; i++) {
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

	return sdw_stream_add_slave(wcd->sdev, &wcd->sconfig, &port_config[0],
				    wcd->active_ports, wcd->sruntime);
}
EXPORT_SYMBOL_GPL(wcd937x_sdw_hw_params);

int wcd937x_sdw_free(struct wcd937x_sdw_priv *wcd,
		     struct snd_pcm_substream *substream,
		     struct snd_soc_dai *dai)
{
	sdw_stream_remove_slave(wcd->sdev, wcd->sruntime);

	return 0;
}
EXPORT_SYMBOL_GPL(wcd937x_sdw_free);

int wcd937x_sdw_set_sdw_stream(struct wcd937x_sdw_priv *wcd,
			       struct snd_soc_dai *dai,
			       void *stream, int direction)
{
	wcd->sruntime = stream;

	return 0;
}
EXPORT_SYMBOL_GPL(wcd937x_sdw_set_sdw_stream);

static int wcd9370_interrupt_callback(struct sdw_slave *slave,
				      struct sdw_slave_intr_status *status)
{
	struct wcd937x_sdw_priv *wcd = dev_get_drvdata(&slave->dev);

	return wcd_interrupt_callback(slave, wcd->slave_irq,
				      WCD937X_DIGITAL_INTR_STATUS_0,
				      WCD937X_DIGITAL_INTR_STATUS_1,
				      WCD937X_DIGITAL_INTR_STATUS_2);
}

static bool wcd937x_rdwr_register(struct device *dev, unsigned int reg)
{
	if (reg <= WCD937X_BASE_ADDRESS)
		return false;

	return reg <= WCD937X_MAX_REGISTER;
}

static bool wcd937x_readable_register(struct device *dev, unsigned int reg)
{
	return wcd937x_rdwr_register(dev, reg);
}

static bool wcd937x_writeable_register(struct device *dev, unsigned int reg)
{
	return wcd937x_rdwr_register(dev, reg);
}

static bool wcd937x_volatile_register(struct device *dev, unsigned int reg)
{
	switch (reg) {
	case WCD937X_DIGITAL_INTR_STATUS_0:
	case WCD937X_DIGITAL_INTR_STATUS_1:
	case WCD937X_DIGITAL_INTR_STATUS_2:
	case WCD937X_DIGITAL_SWR_TX_CLK_RATE:
		return true;
	default:
		return false;
	}
}

static const struct regmap_config wcd937x_regmap_config = {
	.name = "wcd937x_sdw",
	.reg_bits = 32,
	.val_bits = 8,
	.cache_type = REGCACHE_MAPLE,
	.max_register = WCD937X_MAX_REGISTER,
	.readable_reg = wcd937x_readable_register,
	.writeable_reg = wcd937x_writeable_register,
	.volatile_reg = wcd937x_volatile_register,
};

static void wcd937x_parse_channel_mapping(struct device *dev,
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

static const struct sdw_slave_ops wcd9370_slave_ops = {
	.update_status = wcd_update_status,
	.interrupt_callback = wcd9370_interrupt_callback,
	.bus_config = wcd_bus_config,
};

static int wcd9370_probe(struct sdw_slave *pdev,
			 const struct sdw_device_id *id)
{
	struct device *dev = &pdev->dev;
	struct wcd937x_sdw_priv *wcd;
	u8 tx_channel_map[12] = { 0 };
	u8 rx_channel_map[8] = { 0 };
	int ret;

	wcd = devm_kzalloc(dev, sizeof(*wcd), GFP_KERNEL);
	if (!wcd)
		return -ENOMEM;

	if (of_property_present(dev->of_node, "qcom,tx-port-mapping")) {
		wcd->is_tx = true;
		ret = of_property_read_u32_array(dev->of_node, "qcom,tx-port-mapping",
						 &pdev->m_port_map[1],
						 WCD937X_MAX_TX_SWR_PORTS);
		wcd937x_parse_channel_mapping(dev, "qcom,tx-channel-mapping",
					     tx_channel_map,
					     ARRAY_SIZE(tx_channel_map));
	} else {
		ret = of_property_read_u32_array(dev->of_node, "qcom,rx-port-mapping",
						 &pdev->m_port_map[1],
						 WCD937X_MAX_SWR_PORTS);
		wcd937x_parse_channel_mapping(dev, "qcom,rx-channel-mapping",
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

	if (wcd->is_tx) {
		pdev->prop.source_ports = GENMASK(WCD937X_MAX_TX_SWR_PORTS - 1, 0);
		pdev->prop.src_dpn_prop = wcd937x_tx_dpn_prop;
		pdev->prop.wake_capable = true;
		wcd->ch_info = &wcd937x_sdw_tx_ch_info[0];

		wcd->regmap = devm_regmap_init_sdw(pdev, &wcd937x_regmap_config);
		if (IS_ERR(wcd->regmap))
			return dev_err_probe(dev, PTR_ERR(wcd->regmap),
					     "Regmap init failed\n");

		regcache_cache_only(wcd->regmap, true);
	} else {
		pdev->prop.sink_ports = GENMASK(WCD937X_MAX_SWR_PORTS - 1, 0);
		pdev->prop.sink_dpn_prop = wcd937x_rx_dpn_prop;
		wcd->ch_info = &wcd937x_sdw_rx_ch_info[0];
	}

	ret = component_add(dev, &wcd_sdw_component_ops);
	if (ret)
		return ret;

	pm_runtime_set_suspended(dev);

	return 0;
}

static void wcd9370_remove(struct sdw_slave *pdev)
{
	component_del(&pdev->dev, &wcd_sdw_component_ops);
}

static int wcd937x_sdw_runtime_suspend(struct device *dev)
{
	struct wcd937x_sdw_priv *wcd = dev_get_drvdata(dev);

	if (wcd && wcd->regmap) {
		regcache_cache_only(wcd->regmap, true);
		regcache_mark_dirty(wcd->regmap);
	}

	return 0;
}

static int wcd937x_sdw_runtime_resume(struct device *dev)
{
	struct wcd937x_sdw_priv *wcd = dev_get_drvdata(dev);

	if (wcd && wcd->regmap) {
		regcache_cache_only(wcd->regmap, false);
		regcache_sync(wcd->regmap);
	}

	pm_runtime_mark_last_busy(dev);

	return 0;
}

static const struct sdw_device_id wcd9370_slave_id[] = {
	SDW_SLAVE_ENTRY(0x0217, 0x10a, 0),
	{},
};
MODULE_DEVICE_TABLE(sdw, wcd9370_slave_id);

static const struct dev_pm_ops wcd937x_sdw_pm_ops = {
	RUNTIME_PM_OPS(wcd937x_sdw_runtime_suspend,
		       wcd937x_sdw_runtime_resume,
		       NULL)
};

static struct sdw_driver wcd9370_codec_driver = {
	.probe = wcd9370_probe,
	.remove = wcd9370_remove,
	.ops = &wcd9370_slave_ops,
	.id_table = wcd9370_slave_id,
	.driver = {
		.name = "wcd9370-codec",
		.pm = pm_ptr(&wcd937x_sdw_pm_ops),
	},
};
module_sdw_driver(wcd9370_codec_driver);

MODULE_DESCRIPTION("WCD937X SDW codec driver");
MODULE_LICENSE("GPL");
