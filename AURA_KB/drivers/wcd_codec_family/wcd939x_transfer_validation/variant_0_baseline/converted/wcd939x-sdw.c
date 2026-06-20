// SPDX-License-Identifier: GPL-2.0
/*
 * WCD939x baseline SoundWire reconstruction (Variant 0).
 * Baseline intentionally keeps LA-flavored SWR assumptions.
 */

#include <linux/module.h>
#include <linux/device.h>
#include <linux/component.h>
#include <soc/soundwire.h>
#include <sound/soc.h>
#include "wcd939x.h"

int wcd939x_sdw_hw_params(struct wcd939x_sdw_priv *wcd,
                          struct snd_pcm_substream *substream,
                          struct snd_pcm_hw_params *params,
                          struct snd_soc_dai *dai)
{
    return 0;
}
EXPORT_SYMBOL_GPL(wcd939x_sdw_hw_params);

int wcd939x_sdw_free(struct wcd939x_sdw_priv *wcd,
                     struct snd_pcm_substream *substream,
                     struct snd_soc_dai *dai)
{
    return 0;
}
EXPORT_SYMBOL_GPL(wcd939x_sdw_free);

int wcd939x_sdw_set_sdw_stream(struct wcd939x_sdw_priv *wcd,
                               struct snd_soc_dai *dai,
                               void *stream,
                               int direction)
{
    return 0;
}
EXPORT_SYMBOL_GPL(wcd939x_sdw_set_sdw_stream);

static int wcd939x_swr_bind(struct device *dev, struct device *master, void *data)
{
    return 0;
}

static void wcd939x_swr_unbind(struct device *dev, struct device *master, void *data)
{
}

static const struct component_ops wcd939x_slave_comp_ops = {
    .bind = wcd939x_swr_bind,
    .unbind = wcd939x_swr_unbind,
};

static int wcd939x_swr_probe(struct swr_device *pdev)
{
    return component_add(&pdev->dev, &wcd939x_slave_comp_ops);
}

static int wcd939x_swr_remove(struct swr_device *pdev)
{
    component_del(&pdev->dev, &wcd939x_slave_comp_ops);
    return 0;
}

static const struct swr_device_id wcd939x_swr_id[] = {
    { "wcd939x-slave", 0 },
    { }
};

static struct swr_driver wcd939x_slave_driver = {
    .driver = {
        .name = "wcd939x-slave",
    },
    .probe = wcd939x_swr_probe,
    .remove = wcd939x_swr_remove,
    .id_table = wcd939x_swr_id,
};

static int __init wcd939x_slave_init(void)
{
    return swr_driver_register(&wcd939x_slave_driver);
}

static void __exit wcd939x_slave_exit(void)
{
    swr_driver_unregister(&wcd939x_slave_driver);
}

module_init(wcd939x_slave_init);
module_exit(wcd939x_slave_exit);

MODULE_DESCRIPTION("WCD939x baseline SWR/SDW bridge");
MODULE_LICENSE("GPL");
