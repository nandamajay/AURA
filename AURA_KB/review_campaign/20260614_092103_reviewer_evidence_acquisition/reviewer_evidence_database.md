# Reviewer Evidence Database
## Scope
- Campaign: reviewer-only evidence expansion for Qualcomm audio accepted series.
- Sources: existing AURA_KB lore links, accepted commits, and Patchwork API comment records.
- Exclusions: architecture mining, reconstruction, conversion, patch generation.

## Quantitative Summary
- Baseline reviewer evidence rows (existing KB estimate): **19**
- New reviewer evidence rows captured in this campaign: **92**
- Estimated evidence increase: **+73 rows (384.2%)**
- Target reviewers with direct evidence: **4/5**
- Topic coverage count: **9** categories

### Reviewer Coverage
- Mark Brown: 61 comments
- Pierre-Louis Bossart: 10 comments
- Krzysztof Kozlowski: 19 comments
- Vinod Koul: 2 comments
- Bjorn Andersson: 0 comments

### Topic Coverage
- Patch Structure: 55
- SoundWire: 45
- Code Movement: 18
- Objection/Correction: 15
- Runtime PM: 12
- DT: 6
- Commit Message: 6
- General Review: 6
- DAPM: 2

## Series Evidence
| Series | Name | Patches | Accepted | Reviewer Comments | Link |
|---|---|---:|---:|---:|---|
| 181327 | ASoC: don't use snd_pcm_ops | 44 | 42 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=181327 |
| 257693 | ASoC: sdm845: fix soundwire stream handling | 2 | 1 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=257693 |
| 277321 | [v2,1/2] dt-bindings: sound: lpass-cpu: Document DAI subnodes | 2 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=277321 |
| 332711 | ASoC: qcom: Add support for SC7180 lpass variant | 12 | 2 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=332711 |
| 346539 | ASoC: q6dsp: Add support to Codec Ports. | 8 | 8 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=346539 |
| 350083 | ASoC: qcom: lpass-sc7180: Add MODULE_DEVICE_TABLE | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=350083 |
| 351647 | Asoc: qcom: lpass-cpu: Enable MI2S BCLK and LRCLK together | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=351647 |
| 361249 | Qualcomm's lpass-hdmi ASoC driver to support audio over dp port | 7 | 1 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=361249 |
| 366535 | [v2] Asoc: qcom: lpass-cpu: Fix clock disable failure | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=366535 |
| 371353 | [v2] Asoc: qcom: lpass-sc7180: Fix MI2S bitwidth field bit positions | 1 | 1 | 3 | https://patchwork.kernel.org/project/alsa-devel/list/?series=371353 |
| 378089 | ASoC: codecs: add support for LPASS Codec macros | 6 | 6 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=378089 |
| 432165 | ASoC: codecs: add support for LPASS Codec TX and RX macros | 7 | 7 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=432165 |
| 476859 | soundwire: qcom: fix handling of qcom,ports-block-pack-mode | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=476859 |
| 496971 | ASoC: codecs: add wcd938x support | 9 | 9 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=496971 |
| 502535 | [-next] ASoC: codecs: wcd938x: constify static struct snd_soc_dai_ops | 1 | 1 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=502535 |
| 500597 | [v2] ASoC: codecs: wcd938x: remove incorrect module interdependency | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=500597 |
| 501161 | [-next] SoC: codecs: wcd938x: fix boolreturn.cocci warning | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=501161 |
| 504369 | [1/2] ASoC: codecs: wcd938x: fix unused variable warning | 2 | 2 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=504369 |
| 514801 | ASoC: codecs: wcd938x: make sdw dependency explicit in Kconfig | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=514801 |
| 516629 | ASoC: codecs: wcd938x: remove unused port-map reference | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=516629 |
| 516631 | ASoC: codecs: wcd938x: setup irq during component bind | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=516631 |
| 516633 | ASoC: codecs: wcd938x: add Multi Button Headset Control support | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=516633 |
| 526519 | ASoC: codecs: cppcheck warnings | 3 | 3 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=526519 |
| 559169 | ASoC: wcd938x: Fix jack detection issue | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=559169 |
| 559171 | ASoC: codec: wcd938x: Add irq config support | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=559171 |
| 580869 | ASoC: codecs: Qualcomm codecs fixes | 3 | 3 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=580869 |
| 585741 | Kconfig symbol clean-up for sound | 2 | 2 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=585741 |
| 613722 | Add Euro Headset support for wcd938x codec | 2 | 2 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=613722 |
| 614973 | ASoC: codec: wcd938x: Update CTIA/OMTP switch control | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=614973 |
| 616303 | ASoC: codec: add pm runtime support for Qualcomm codecs | 10 | 2 | 4 | https://patchwork.kernel.org/project/alsa-devel/list/?series=616303 |
| 616854 | ASoC: codecs: qcom fix validation failures | 9 | 7 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=616854 |
| 617524 | ASoC: codecs: add pm runtime support for Qualcomm codecs | 16 | 15 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=617524 |
| 620423 | ASoC: qcom: select correct WCD938X config for SC7280 | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=620423 |
| 625078 | Update dt-bindings for sc7280 platform | 3 | 3 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=625078 |
| 642721 | [v2] ASoC: qcom: soundwire: Add support for controlling audio CGCR from HLOS | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=642721 |
| 654926 | ASoC: codecs: add WSA883x support | 4 | 3 | 3 | https://patchwork.kernel.org/project/alsa-devel/list/?series=654926 |
| 655083 | [v2] ASoC: codecs: wsa883x: add control, dapm widgets and map | 1 | 0 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=655083 |
| 655415 | [v3] ASoC: codecs: wsa883x: add control, dapm widgets and map | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=655415 |
| 655429 | [1/2] ASoC: codecs: wsa881x: handle timeouts in resume path | 2 | 2 | 2 | https://patchwork.kernel.org/project/alsa-devel/list/?series=655429 |
| 655823 | ASoC: codecs: wsa883x: add missing break statement | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=655823 |
| 655880 | ASoC: codecs: wsa883x: fix fallthrough error | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=655880 |
| 656571 | [-next] ASoC: codecs: wsa883x: fix warning using-module-alias-sdw.cocci | 1 | 1 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=656571 |
| 667414 | soundwire: qcom: remove duplicate reset control get | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=667414 |
| 668609 | soundwire: qcom: remove unneeded check | 1 | 1 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=668609 |
| 674589 | ASoC: codecs: qcom add support for SM8450 and SC8280XP | 12 | 12 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=674589 |
| 685508 | ASoC: qcom: SND_SOC_SC7180 optionally depends on SOUNDWIRE | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=685508 |
| 692989 | [v2] ASoC: codecs: wsa883x: use correct header file | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=692989 |
| 693713 | ASoC: codecs: wsa883x: Use proper shutdown GPIO values | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=693713 |
| 693714 | [1/2] ASoC: codecs: wsa883x: Shutdown on error path | 2 | 2 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=693714 |
| 694081 | [v2,1/2] ASoC: dt-bindings: qcom, wsa883x: Use correct SD_N polarity | 2 | 2 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=694081 |
| 708017 | ASoC: qcom: Fix building APQ8016 machine driver without SOUNDWIRE | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=708017 |
| 708222 | [1/8] ASoC: codecs: wsa883x: Simplify &pdev->dev in probe | 8 | 4 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=708222 |
| 715105 | ASoC: codecs: wsa883x: correct playback min/max rates | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=715105 |
| 733249 | ASoC: qcom: fixes for Click/Pop Noise | 4 | 2 | 5 | https://patchwork.kernel.org/project/alsa-devel/list/?series=733249 |
| 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | 2 | 2 | 6 | https://patchwork.kernel.org/project/alsa-devel/list/?series=750308 |
| 754991 | ASoC: codecs: wsa883x: use existing define instead of raw value | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=754991 |
| 755223 | [1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | 2 | 0 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=755223 |
| 756050 | [v2,1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | 2 | 0 | 3 | https://patchwork.kernel.org/project/alsa-devel/list/?series=756050 |
| 756224 | [v3,1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | 2 | 0 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=756224 |
| 757854 | [v4,1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | 2 | 2 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=757854 |
| 764996 | ASoC: qcom: Use the maple tree register cache | 4 | 4 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=764996 |
| 804936 | [1/2] ASoC: qcom: Add helper for allocating Soundwire stream runtime | 2 | 2 | 7 | https://patchwork.kernel.org/project/alsa-devel/list/?series=804936 |
| 808754 | ASoC: codec: wsa884x: make use of new mute_unmute_on_trigger flag | 1 | 1 | 2 | https://patchwork.kernel.org/project/alsa-devel/list/?series=808754 |
| 818769 | ASoC: qcom: volume fixes and codec cleanups | 4 | 4 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=818769 |
| 820841 | reset: gpio: ASoC: shared GPIO resets | 6 | 2 | 6 | https://patchwork.kernel.org/project/alsa-devel/list/?series=820841 |
| 828232 | [RESEND,v6,v6,1/2] ASoC: dt-bindings: qcom,wsa8840: Add reset-gpios for shared line | 2 | 2 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=828232 |
| 866183 | ASoC: codecs: wsa88xx: add support for static port mapping. | 6 | 4 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=866183 |
| 868119 | ASoC: Constify struct regmap_config | 9 | 9 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=868119 |
| 870132 | ASoC: codecs: wsa88xx: Few cleanups | 4 | 4 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=870132 |
| 873809 | ASoC: codecs: wsa88xx and wcd93xx: Soundwire port non-functional cleanup | 7 | 7 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=873809 |
| 874099 | ASoC: codecs: wcd93xx/wsa88xx: Correct Soundwire ports mask | 6 | 6 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=874099 |
| 878174 | [v3] ASoC: codecs: wsa884x: Implement temperature reading and hwmon | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=878174 |
| 897379 | ASoC: qcom: sdm845: add missing soundwire runtime stream alloc | 1 | 1 | 2 | https://patchwork.kernel.org/project/alsa-devel/list/?series=897379 |
| 898414 | ASoC: qcom: Select missing common Soundwire module code on SDM845 | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=898414 |
| 898415 | [v2] ASoC: qcom: sc7280: Fix missing Soundwire runtime stream alloc | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=898415 |
| 931174 | Add static channel mapping between soundwire master and slave | 4 | 4 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=931174 |
| 936274 | [v2] ASoC: codecs: wsa883x: Implement temperature reading and hwmon | 1 | 1 | 2 | https://patchwork.kernel.org/project/alsa-devel/list/?series=936274 |
| 936283 | ASoC: codecs: wsa884x: report temps to hwmon in millidegree of Celsius | 1 | 1 | 1 | https://patchwork.kernel.org/project/alsa-devel/list/?series=936283 |
| 943235 | ASoC: codecs: wsa88xx: Correct VI sense channel mask | 2 | 2 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=943235 |
| 944568 | ASoC: Convert to modern PM macros | 88 | 88 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=944568 |
| 1011062 | ASoC: use snd_kcontrol_chip() instead of snd_soc_kcontrol_component() | 139 | 139 | 0 | https://patchwork.kernel.org/project/alsa-devel/list/?series=1011062 |
| 1037892 | ASoC: codecs: wsa88xx: fix codec initialisation | 4 | 4 | 7 | https://patchwork.kernel.org/project/alsa-devel/list/?series=1037892 |

## Extracted Reviewer Comment Evidence
| Date | Reviewer | Series | Patch | Topics | Requested Change Signals | Evidence |
|---|---|---|---|---|---|---|
| 2020-05-05 | Mark Brown | 277321 | [v2,1/2] dt-bindings: sound: lpass-cpu: Document DAI subnodes | DT, Patch Structure | Adjust DT schema/binding | patch:11510017 comment:23331733 (https://patchwork.kernel.org/project/alsa-devel/patch/20200425184657.121991-1-stephan@gerhold.net/) |
| 2020-09-17 | Mark Brown | 350083 | ASoC: qcom: lpass-sc7180: Add MODULE_DEVICE_TABLE | Patch Structure | None-explicit | patch:11780381 comment:23624223 (https://patchwork.kernel.org/project/alsa-devel/patch/20200916111545.1.I4c3758817d94c433bafeac344a395e21ea6657e3@changeid/) |
| 2020-09-25 | Mark Brown | 351647 | Asoc: qcom: lpass-cpu: Enable MI2S BCLK and LRCLK together | Patch Structure, Code Movement | Move code to proper file/layer | patch:11785535 comment:23645509 (https://patchwork.kernel.org/project/alsa-devel/patch/1600448073-6709-1-git-send-email-srivasam@codeaurora.org/) |
| 2020-10-28 | Mark Brown | 371353 | [v2] Asoc: qcom: lpass-sc7180: Fix MI2S bitwidth field bit positions | Patch Structure, Commit Message | None-explicit | patch:11860083 comment:23717423 (https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/) |
| 2020-10-28 | Mark Brown | 371353 | [v2] Asoc: qcom: lpass-sc7180: Fix MI2S bitwidth field bit positions | Patch Structure | None-explicit | patch:11860083 comment:23717445 (https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/) |
| 2020-10-29 | Mark Brown | 366535 | [v2] Asoc: qcom: lpass-cpu: Fix clock disable failure | Runtime PM, Patch Structure | None-explicit | patch:11843861 comment:23720097 (https://patchwork.kernel.org/project/alsa-devel/patch/1603098363-9251-1-git-send-email-srivasam@codeaurora.org/) |
| 2020-10-29 | Mark Brown | 371353 | [v2] Asoc: qcom: lpass-sc7180: Fix MI2S bitwidth field bit positions | Patch Structure | None-explicit | patch:11860083 comment:23720101 (https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/) |
| 2021-05-11 | Vinod Koul | 476859 | soundwire: qcom: fix handling of qcom,ports-block-pack-mode | SoundWire, Patch Structure | Fix SoundWire modeling | patch:12238055 comment:24168653 (https://patchwork.kernel.org/project/alsa-devel/patch/20210504125909.16108-1-srinivas.kandagatla@linaro.org/) |
| 2021-06-15 | Mark Brown | 500597 | [v2] ASoC: codecs: wcd938x: remove incorrect module interdependency | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:12321535 comment:24251169 (https://patchwork.kernel.org/project/alsa-devel/patch/20210615132829.23067-1-srinivas.kandagatla@linaro.org/) |
| 2021-06-16 | Mark Brown | 501161 | [-next] SoC: codecs: wcd938x: fix boolreturn.cocci warning | Patch Structure | None-explicit | patch:12323779 comment:24254967 (https://patchwork.kernel.org/project/alsa-devel/patch/1623811535-15841-1-git-send-email-yang.lee@linux.alibaba.com/) |
| 2021-06-22 | Mark Brown | 504369 | [1/2] ASoC: codecs: wcd938x: fix unused variable warning | Patch Structure | None-explicit | patch:12334841 comment:24268367 (https://patchwork.kernel.org/project/alsa-devel/patch/20210621134502.19537-1-srinivas.kandagatla@linaro.org/) |
| 2021-07-14 | Mark Brown | 514801 | ASoC: codecs: wcd938x: make sdw dependency explicit in Kconfig | SoundWire, Patch Structure | Fix SoundWire modeling | patch:12374047 comment:24311489 (https://patchwork.kernel.org/project/alsa-devel/patch/20210713140417.23693-1-srinivas.kandagatla@linaro.org/) |
| 2021-07-16 | Mark Brown | 516629 | ASoC: codecs: wcd938x: remove unused port-map reference | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:12381993 comment:24316777 (https://patchwork.kernel.org/project/alsa-devel/patch/20210716105612.5284-1-srinivas.kandagatla@linaro.org/) |
| 2021-07-16 | Mark Brown | 516631 | ASoC: codecs: wcd938x: setup irq during component bind | SoundWire, Patch Structure | Fix SoundWire modeling | patch:12381995 comment:24316781 (https://patchwork.kernel.org/project/alsa-devel/patch/20210716105735.6073-1-srinivas.kandagatla@linaro.org/) |
| 2021-08-06 | Mark Brown | 516633 | ASoC: codecs: wcd938x: add Multi Button Headset Control support | Patch Structure | None-explicit | patch:12381997 comment:24362699 (https://patchwork.kernel.org/project/alsa-devel/patch/20210716105918.7301-1-srinivas.kandagatla@linaro.org/) |
| 2021-10-07 | Mark Brown | 559171 | ASoC: codec: wcd938x: Add irq config support | Patch Structure | None-explicit | patch:12541953 comment:24503425 (https://patchwork.kernel.org/project/alsa-devel/patch/1633614675-27122-1-git-send-email-srivasam@codeaurora.org/) |
| 2021-10-07 | Mark Brown | 559169 | ASoC: wcd938x: Fix jack detection issue | Patch Structure | None-explicit | patch:12541951 comment:24503447 (https://patchwork.kernel.org/project/alsa-devel/patch/1633614619-27026-1-git-send-email-srivasam@codeaurora.org/) |
| 2022-02-17 | Mark Brown | 614973 | ASoC: codec: wcd938x: Update CTIA/OMTP switch control | Patch Structure, Code Movement | Move code to proper file/layer | patch:12748610 comment:24742828 (https://patchwork.kernel.org/project/alsa-devel/patch/1645017892-12522-1-git-send-email-quic_srivasam@quicinc.com/) |
| 2022-02-21 | Mark Brown | 616303 | [01/10] ASoC: codecs: va-macro: add runtime pm support | Runtime PM | None-explicit | patch:12753616 comment:24747183 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-2-srinivas.kandagatla@linaro.org/) |
| 2022-02-21 | Mark Brown | 616303 | [09/10] ASoC: codecs: tx-macro: setup soundwire clks correctly | SoundWire, Patch Structure, Commit Message | Fix SoundWire modeling, Improve commit message | patch:12753626 comment:24747206 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-10-srinivas.kandagatla@linaro.org/) |
| 2022-02-21 | Mark Brown | 616303 | [09/10] ASoC: codecs: tx-macro: setup soundwire clks correctly | Runtime PM, SoundWire, Patch Structure, Commit Message | Fix Runtime PM flow, Fix SoundWire modeling, Improve commit message | patch:12753626 comment:24747312 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-10-srinivas.kandagatla@linaro.org/) |
| 2022-02-22 | Mark Brown | 616854 | [v2,3/9] ASoC: codecs: tx-macro: fix accessing array out of bounds for enum type | Patch Structure | None-explicit | patch:12755816 comment:24748938 (https://patchwork.kernel.org/project/alsa-devel/patch/20220222183212.11580-4-srinivas.kandagatla@linaro.org/) |
| 2022-02-22 | Pierre-Louis Bossart | 616303 | [05/10] ASoC: codecs: wsa881x: add runtime pm support | Runtime PM, SoundWire, Objection/Correction | Fix Runtime PM flow, Fix SoundWire modeling | patch:12753622 comment:24749034 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-6-srinivas.kandagatla@linaro.org/) |
| 2022-02-24 | Pierre-Louis Bossart | 617524 | [v2,14/16] ASoC: codecs: wsa881x: add runtime pm support | Runtime PM, SoundWire, Commit Message | Fix SoundWire modeling, Improve commit message | patch:12758408 comment:24752554 (https://patchwork.kernel.org/project/alsa-devel/patch/20220224111718.6264-15-srinivas.kandagatla@linaro.org/) |
| 2022-03-07 | Mark Brown | 620423 | ASoC: qcom: select correct WCD938X config for SC7280 | SoundWire, Patch Structure | Fix SoundWire modeling | patch:12769408 comment:24769100 (https://patchwork.kernel.org/project/alsa-devel/patch/20220304160934.32010-1-srinivas.kandagatla@linaro.org/) |
| 2022-06-07 | Mark Brown | 642721 | [v2] ASoC: qcom: soundwire: Add support for controlling audio CGCR from HLOS | SoundWire, Patch Structure | Fix SoundWire modeling | patch:12853622 comment:24884624 (https://patchwork.kernel.org/project/alsa-devel/patch/1652877755-25120-1-git-send-email-quic_srivasam@quicinc.com/) |
| 2022-06-29 | Mark Brown | 654926 | [3/4] ASoC: codecs: wsa883x: add control, dapm widgets and map | DAPM | None-explicit | patch:12899625 comment:24916294 (https://patchwork.kernel.org/project/alsa-devel/patch/20220629090644.67982-4-srinivas.kandagatla@linaro.org/) |
| 2022-06-29 | Mark Brown | 655083 | [v2] ASoC: codecs: wsa883x: add control, dapm widgets and map | General Review | None-explicit | patch:12900259 comment:24916670 (https://patchwork.kernel.org/project/alsa-devel/patch/20220629145831.77868-1-srinivas.kandagatla@linaro.org/) |
| 2022-06-29 | Pierre-Louis Bossart | 654926 | [2/4] ASoC: codecs: add wsa883x amplifier support | Runtime PM, SoundWire, Objection/Correction | Fix SoundWire modeling | patch:12899623 comment:24916678 (https://patchwork.kernel.org/project/alsa-devel/patch/20220629090644.67982-3-srinivas.kandagatla@linaro.org/) |
| 2022-06-29 | Pierre-Louis Bossart | 654926 | [2/4] ASoC: codecs: add wsa883x amplifier support | SoundWire, Objection/Correction | Fix SoundWire modeling | patch:12899623 comment:24916911 (https://patchwork.kernel.org/project/alsa-devel/patch/20220629090644.67982-3-srinivas.kandagatla@linaro.org/) |
| 2022-06-30 | Pierre-Louis Bossart | 655429 | [1/2] ASoC: codecs: wsa881x: handle timeouts in resume path | Runtime PM, SoundWire, Patch Structure | Fix Runtime PM flow, Fix SoundWire modeling | patch:12901805 comment:24918606 (https://patchwork.kernel.org/project/alsa-devel/patch/20220630130023.9308-1-srinivas.kandagatla@linaro.org/) |
| 2022-06-30 | Mark Brown | 655415 | [v3] ASoC: codecs: wsa883x: add control, dapm widgets and map | DAPM, Patch Structure | None-explicit | patch:12901777 comment:24918735 (https://patchwork.kernel.org/project/alsa-devel/patch/20220630123633.8047-1-srinivas.kandagatla@linaro.org/) |
| 2022-06-30 | Mark Brown | 655429 | [1/2] ASoC: codecs: wsa881x: handle timeouts in resume path | Runtime PM, SoundWire, Patch Structure | Fix SoundWire modeling | patch:12901805 comment:24918936 (https://patchwork.kernel.org/project/alsa-devel/patch/20220630130023.9308-1-srinivas.kandagatla@linaro.org/) |
| 2022-07-01 | Mark Brown | 655823 | ASoC: codecs: wsa883x: add missing break statement | Patch Structure | None-explicit | patch:12903271 comment:24921048 (https://patchwork.kernel.org/project/alsa-devel/patch/20220701125515.32332-1-srinivas.kandagatla@linaro.org/) |
| 2022-07-01 | Mark Brown | 655880 | ASoC: codecs: wsa883x: fix fallthrough error | Patch Structure | None-explicit | patch:12903536 comment:24921134 (https://patchwork.kernel.org/project/alsa-devel/patch/20220701155930.262278-1-trix@redhat.com/) |
| 2022-08-23 | Vinod Koul | 667414 | soundwire: qcom: remove duplicate reset control get | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:12942876 comment:24980134 (https://patchwork.kernel.org/project/alsa-devel/patch/20220814123800.31200-1-srinivas.kandagatla@linaro.org/) |
| 2022-10-18 | Mark Brown | 685508 | ASoC: qcom: SND_SOC_SC7180 optionally depends on SOUNDWIRE | SoundWire, Patch Structure | Fix SoundWire modeling | patch:13007541 comment:25050594 (https://patchwork.kernel.org/project/alsa-devel/patch/20221015001228.18990-1-rdunlap@infradead.org/) |
| 2022-11-10 | Krzysztof Kozlowski | 693713 | ASoC: codecs: wsa883x: Use proper shutdown GPIO values | Patch Structure | None-explicit | patch:13037726 comment:25084269 (https://patchwork.kernel.org/project/alsa-devel/patch/20221109163740.1158785-1-krzysztof.kozlowski@linaro.org/) |
| 2022-11-11 | Mark Brown | 694081 | [v2,1/2] ASoC: dt-bindings: qcom, wsa883x: Use correct SD_N polarity | DT, Patch Structure, Commit Message | Adjust DT schema/binding | patch:13038802 comment:25086581 (https://patchwork.kernel.org/project/alsa-devel/patch/20221110133512.478831-1-krzysztof.kozlowski@linaro.org/) |
| 2022-11-11 | Mark Brown | 692989 | [v2] ASoC: codecs: wsa883x: use correct header file | Patch Structure | None-explicit | patch:13035557 comment:25086582 (https://patchwork.kernel.org/project/alsa-devel/patch/20221108001829.5100-1-rdunlap@infradead.org/) |
| 2022-11-17 | Mark Brown | 693714 | [1/2] ASoC: codecs: wsa883x: Shutdown on error path | Patch Structure | None-explicit | patch:13037727 comment:25094620 (https://patchwork.kernel.org/project/alsa-devel/patch/20221109163759.1158837-1-krzysztof.kozlowski@linaro.org/) |
| 2023-01-09 | Mark Brown | 708017 | ASoC: qcom: Fix building APQ8016 machine driver without SOUNDWIRE | SoundWire, Patch Structure | Fix SoundWire modeling | patch:13086030 comment:25152702 (https://patchwork.kernel.org/project/alsa-devel/patch/20221231115506.82991-1-stephan@gerhold.net/) |
| 2023-01-16 | Mark Brown | 708222 | [1/8] ASoC: codecs: wsa883x: Simplify &pdev->dev in probe | Patch Structure | None-explicit | patch:13086697 comment:25163833 (https://patchwork.kernel.org/project/alsa-devel/patch/20230102114152.297305-1-krzysztof.kozlowski@linaro.org/) |
| 2023-01-26 | Mark Brown | 715105 | ASoC: codecs: wsa883x: correct playback min/max rates | Patch Structure | None-explicit | patch:13113997 comment:25181474 (https://patchwork.kernel.org/project/alsa-devel/patch/20230124123049.285395-1-krzysztof.kozlowski@linaro.org/) |
| 2023-03-23 | Mark Brown | 733249 | [3/4] ASoC: codecs: wsa883x: mute/unmute PA in correct sequence | Runtime PM, SoundWire | Fix SoundWire modeling | patch:13185869 comment:25266868 (https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/) |
| 2023-03-23 | Pierre-Louis Bossart | 733249 | [3/4] ASoC: codecs: wsa883x: mute/unmute PA in correct sequence | Runtime PM, SoundWire | Fix SoundWire modeling | patch:13185869 comment:25266965 (https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/) |
| 2023-03-24 | Mark Brown | 733249 | [3/4] ASoC: codecs: wsa883x: mute/unmute PA in correct sequence | SoundWire | Fix SoundWire modeling | patch:13185869 comment:25267372 (https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/) |
| 2023-05-23 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | SoundWire | Fix SoundWire modeling | patch:13252569 comment:25347988 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-05-24 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | SoundWire | Fix SoundWire modeling | patch:13252569 comment:25349292 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-05-24 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | SoundWire, Objection/Correction | Fix SoundWire modeling | patch:13252569 comment:25349442 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-05-24 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | General Review | None-explicit | patch:13252569 comment:25349493 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-05-24 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | SoundWire, Patch Structure | Fix SoundWire modeling | patch:13252569 comment:25349608 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-06-05 | Mark Brown | 750308 | [1/2] ASoC: codecs: wsa883x: do not set can_multi_write flag | General Review | None-explicit | patch:13252569 comment:25366177 (https://patchwork.kernel.org/project/alsa-devel/patch/20230523154605.4284-1-srinivas.kandagatla@linaro.org/) |
| 2023-06-07 | Mark Brown | 754991 | ASoC: codecs: wsa883x: use existing define instead of raw value | Patch Structure | None-explicit | patch:13271022 comment:25372085 (https://patchwork.kernel.org/project/alsa-devel/patch/20230607171326.179527-1-krzysztof.kozlowski@linaro.org/) |
| 2023-06-08 | Krzysztof Kozlowski | 755223 | [1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | DT, SoundWire, Commit Message | Adjust DT schema/binding, Fix SoundWire modeling | patch:13271787 comment:25373072 (https://patchwork.kernel.org/project/alsa-devel/patch/20230608085023.141745-1-krzysztof.kozlowski@linaro.org/) |
| 2023-06-11 | Mark Brown | 756050 | [v2,2/2] ASoC: codecs: wsa884x: Add WSA884x family of speakers | Objection/Correction | None-explicit | patch:13275179 comment:25376962 (https://patchwork.kernel.org/project/alsa-devel/patch/20230611102657.74714-2-krzysztof.kozlowski@linaro.org/) |
| 2023-06-12 | Krzysztof Kozlowski | 756050 | [v2,2/2] ASoC: codecs: wsa884x: Add WSA884x family of speakers | Objection/Correction | None-explicit | patch:13275179 comment:25377306 (https://patchwork.kernel.org/project/alsa-devel/patch/20230611102657.74714-2-krzysztof.kozlowski@linaro.org/) |
| 2023-06-12 | Mark Brown | 756050 | [v2,2/2] ASoC: codecs: wsa884x: Add WSA884x family of speakers | Objection/Correction | None-explicit | patch:13275179 comment:25377997 (https://patchwork.kernel.org/project/alsa-devel/patch/20230611102657.74714-2-krzysztof.kozlowski@linaro.org/) |
| 2023-06-15 | Krzysztof Kozlowski | 756224 | [v3,2/2] ASoC: codecs: wsa884x: Add WSA884x family of speakers | SoundWire, Patch Structure, Objection/Correction | Fix SoundWire modeling | patch:13276224 comment:25384465 (https://patchwork.kernel.org/project/alsa-devel/patch/20230612095716.118631-2-krzysztof.kozlowski@linaro.org/) |
| 2023-06-21 | Mark Brown | 757854 | [v4,1/2] ASoC: dt-bindings: qcom,wsa8840: Add WSA884x family of speakers | DT, Patch Structure | Adjust DT schema/binding | patch:13282700 comment:25392390 (https://patchwork.kernel.org/project/alsa-devel/patch/20230616115751.392886-1-krzysztof.kozlowski@linaro.org/) |
| 2023-10-25 | Mark Brown | 733249 | [3/4] ASoC: codecs: wsa883x: mute/unmute PA in correct sequence | Patch Structure | None-explicit | patch:13185869 comment:25570090 (https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/) |
| 2023-10-26 | Mark Brown | 733249 | [3/4] ASoC: codecs: wsa883x: mute/unmute PA in correct sequence | Patch Structure | None-explicit | patch:13185869 comment:25571967 (https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/) |
| 2023-11-28 | Krzysztof Kozlowski | 804936 | [2/2] ASoC: qcom: Move Soundwire runtime stream alloc to soundcards | SoundWire | Fix SoundWire modeling | patch:13471453 comment:25611713 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-2-krzysztof.kozlowski@linaro.org/) |
| 2023-11-28 | Pierre-Louis Bossart | 804936 | [1/2] ASoC: qcom: Add helper for allocating Soundwire stream runtime | SoundWire, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13471452 comment:25611863 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/) |
| 2023-11-28 | Pierre-Louis Bossart | 804936 | [2/2] ASoC: qcom: Move Soundwire runtime stream alloc to soundcards | SoundWire | Fix SoundWire modeling | patch:13471453 comment:25611864 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-2-krzysztof.kozlowski@linaro.org/) |
| 2023-11-28 | Pierre-Louis Bossart | 804936 | [2/2] ASoC: qcom: Move Soundwire runtime stream alloc to soundcards | SoundWire | Fix SoundWire modeling | patch:13471453 comment:25611865 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-2-krzysztof.kozlowski@linaro.org/) |
| 2023-11-29 | Krzysztof Kozlowski | 804936 | [1/2] ASoC: qcom: Add helper for allocating Soundwire stream runtime | SoundWire, Code Movement, Objection/Correction | Fix SoundWire modeling, Move code to proper file/layer | patch:13471452 comment:25613818 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/) |
| 2023-11-29 | Pierre-Louis Bossart | 804936 | [1/2] ASoC: qcom: Add helper for allocating Soundwire stream runtime | SoundWire, Code Movement, Objection/Correction | Fix SoundWire modeling, Move code to proper file/layer | patch:13471452 comment:25614050 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/) |
| 2023-11-30 | Mark Brown | 804936 | [1/2] ASoC: qcom: Add helper for allocating Soundwire stream runtime | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13471452 comment:25615253 (https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/) |
| 2023-12-11 | Krzysztof Kozlowski | 808754 | ASoC: codec: wsa884x: make use of new mute_unmute_on_trigger flag | SoundWire, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13487056 comment:25631629 (https://patchwork.kernel.org/project/alsa-devel/patch/20231211-topic-sm8x50-upstream-wsa884x-fix-plop-v1-1-0dc630a19172@linaro.org/) |
| 2023-12-11 | Mark Brown | 808754 | ASoC: codec: wsa884x: make use of new mute_unmute_on_trigger flag | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13487056 comment:25632170 (https://patchwork.kernel.org/project/alsa-devel/patch/20231211-topic-sm8x50-upstream-wsa884x-fix-plop-v1-1-0dc630a19172@linaro.org/) |
| 2024-01-31 | Krzysztof Kozlowski | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | DT, Patch Structure, Code Movement, Objection/Correction | Adjust DT schema/binding | patch:13535430 comment:25691099 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-01-31 | Krzysztof Kozlowski | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | DT, Patch Structure, Code Movement, Objection/Correction | Adjust DT schema/binding | patch:13535430 comment:25691100 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-01-31 | Mark Brown | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | Patch Structure, Objection/Correction | None-explicit | patch:13535430 comment:25691550 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-01-31 | Krzysztof Kozlowski | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | Patch Structure, Objection/Correction | None-explicit | patch:13535430 comment:25691551 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-01-31 | Mark Brown | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | General Review | None-explicit | patch:13535430 comment:25691614 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-02-12 | Krzysztof Kozlowski | 820841 | [v6,4/6] reset: Instantiate reset GPIO controller for shared reset-gpios | Code Movement | None-explicit | patch:13535430 comment:25708899 (https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/) |
| 2024-08-29 | Mark Brown | 878174 | [v3] ASoC: codecs: wsa884x: Implement temperature reading and hwmon | Patch Structure | None-explicit | patch:13758697 comment:26002573 (https://patchwork.kernel.org/project/alsa-devel/patch/20240809110122.137761-1-krzysztof.kozlowski@linaro.org/) |
| 2024-10-10 | Krzysztof Kozlowski | 897379 | ASoC: qcom: sdm845: add missing soundwire runtime stream alloc | SoundWire, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13829277 comment:26061540 (https://patchwork.kernel.org/project/alsa-devel/patch/20241009213922.999355-1-alexey.klimov@linaro.org/) |
| 2024-10-10 | Mark Brown | 897379 | ASoC: qcom: sdm845: add missing soundwire runtime stream alloc | SoundWire, Patch Structure | Fix SoundWire modeling | patch:13829277 comment:26062972 (https://patchwork.kernel.org/project/alsa-devel/patch/20241009213922.999355-1-alexey.klimov@linaro.org/) |
| 2024-10-12 | Mark Brown | 898414 | ASoC: qcom: Select missing common Soundwire module code on SDM845 | SoundWire, Patch Structure | Fix SoundWire modeling | patch:13833277 comment:26065923 (https://patchwork.kernel.org/project/alsa-devel/patch/20241012100957.129103-1-krzysztof.kozlowski@linaro.org/) |
| 2024-10-22 | Mark Brown | 898415 | [v2] ASoC: qcom: sc7280: Fix missing Soundwire runtime stream alloc | SoundWire, Patch Structure, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:13833278 comment:26084046 (https://patchwork.kernel.org/project/alsa-devel/patch/20241012101108.129476-1-krzysztof.kozlowski@linaro.org/) |
| 2025-02-24 | Mark Brown | 936274 | [v2] ASoC: codecs: wsa883x: Implement temperature reading and hwmon | General Review | None-explicit | patch:13984792 comment:26260278 (https://patchwork.kernel.org/project/alsa-devel/patch/20250221032141.1206902-1-alexey.klimov@linaro.org/) |
| 2025-03-04 | Mark Brown | 936283 | ASoC: codecs: wsa884x: report temps to hwmon in millidegree of Celsius | Patch Structure | None-explicit | patch:13984804 comment:26276261 (https://patchwork.kernel.org/project/alsa-devel/patch/20250221044024.1207921-1-alexey.klimov@linaro.org/) |
| 2025-03-04 | Mark Brown | 936274 | [v2] ASoC: codecs: wsa883x: Implement temperature reading and hwmon | Patch Structure | None-explicit | patch:13984792 comment:26276262 (https://patchwork.kernel.org/project/alsa-devel/patch/20250221032141.1206902-1-alexey.klimov@linaro.org/) |
| 2026-01-02 | Krzysztof Kozlowski | 1037892 | [3/4] ASoC: codecs: wsa884x: fix codec initialisation | SoundWire, Code Movement | Fix SoundWire modeling, Move code to proper file/layer | patch:14365029 comment:26716206 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-4-johan@kernel.org/) |
| 2026-01-02 | Krzysztof Kozlowski | 1037892 | [3/4] ASoC: codecs: wsa884x: fix codec initialisation | Runtime PM, SoundWire, Code Movement | Fix Runtime PM flow, Fix SoundWire modeling, Move code to proper file/layer | patch:14365029 comment:26716228 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-4-johan@kernel.org/) |
| 2026-01-02 | Krzysztof Kozlowski | 1037892 | [3/4] ASoC: codecs: wsa884x: fix codec initialisation | Runtime PM, Objection/Correction | Fix Runtime PM flow | patch:14365029 comment:26716303 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-4-johan@kernel.org/) |
| 2026-01-05 | Krzysztof Kozlowski | 1037892 | [3/4] ASoC: codecs: wsa884x: fix codec initialisation | SoundWire | Fix SoundWire modeling | patch:14365029 comment:26717950 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-4-johan@kernel.org/) |
| 2026-01-05 | Krzysztof Kozlowski | 1037892 | [1/4] ASoC: codecs: wsa883x: fix unnecessary initialisation | SoundWire | Fix SoundWire modeling | patch:14365028 comment:26717951 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-2-johan@kernel.org/) |
| 2026-01-05 | Krzysztof Kozlowski | 1037892 | [2/4] ASoC: codecs: wsa881x: fix unnecessary initialisation | SoundWire | Fix SoundWire modeling | patch:14365027 comment:26717952 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-3-johan@kernel.org/) |
| 2026-01-05 | Krzysztof Kozlowski | 1037892 | [4/4] ASoC: codecs: wsa883x: suppress variant printk | General Review | None-explicit | patch:14365030 comment:26717969 (https://patchwork.kernel.org/project/alsa-devel/patch/20260102111413.9605-5-johan@kernel.org/) |

## Driver-Hint Distribution (from series/patch subject matching)
- lpass_generic: 7 reviewer-comment rows
- wcd938x: 11 reviewer-comment rows
- lpass_va_macro: 1 reviewer-comment rows
- lpass_tx_macro: 3 reviewer-comment rows
- wsa883x: 29 reviewer-comment rows
- wsa884x: 14 reviewer-comment rows
