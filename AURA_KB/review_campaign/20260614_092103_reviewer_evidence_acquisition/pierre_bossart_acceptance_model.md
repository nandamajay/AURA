# Pierre-Louis Bossart Acceptance Model

## Evidence Strength
- Direct reviewer comments captured: **10**
- Confidence: **MEDIUM (78/100)**

## Observed Review Focus
- SoundWire: 10
- Runtime PM: 5
- Objection/Correction: 4
- Code Movement: 2
- Commit Message: 1
- Patch Structure: 1

## Common Requested Changes
- Fix SoundWire modeling: 10
- Fix Runtime PM flow: 2
- Move code to proper file/layer: 2
- Improve commit message: 1

## Acceptance Signals
- Patches tend to converge when reviewer-requested correctness/style updates are explicitly addressed in vN changelog and split cleanly when requested.
- Evidence basis: Patchwork comment records + accepted states in same series.

## Evidence Examples
- Series 616303 patch 12753622: https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-6-srinivas.kandagatla@linaro.org/
  - Topics: Runtime PM, SoundWire, Objection/Correction; Requests: Fix Runtime PM flow, Fix SoundWire modeling
  - Comment excerpt: "On 2/21/22 07:10, Srinivas Kandagatla wrote: > WSA881x codecs can not cope up with clk stop and requires a full reset after suspend. isn't clock stop mode0 a peripheral requirement in SoundWire 1.x? I don't see any permission to skip this mode, the only thing I see in the spec is"
- Series 617524 patch 12758408: https://patchwork.kernel.org/project/alsa-devel/patch/20220224111718.6264-15-srinivas.kandagatla@linaro.org/
  - Topics: Runtime PM, SoundWire, Commit Message; Requests: Fix SoundWire modeling, Improve commit message
  - Comment excerpt: "On 2/24/22 05:17, Srinivas Kandagatla wrote: > WSA881x codecs can not cope up with clk stop and requires a full reset after suspend. > WSA SoundWire Controller connected to this instances do a full soft reset on suspend. is it the manager or peripheral that cannot cope with clock"
- Series 654926 patch 12899623: https://patchwork.kernel.org/project/alsa-devel/patch/20220629090644.67982-3-srinivas.kandagatla@linaro.org/
  - Topics: Runtime PM, SoundWire, Objection/Correction; Requests: Fix SoundWire modeling
  - Comment excerpt: "> +/* 4 ports */ > +static struct sdw_dpn_prop wsa_sink_dpn_prop[WSA883X_MAX_SWR_PORTS] = { > + { > + /* DAC */ > + .num = 1, > + .type = SDW_DPN_SIMPLE, > + .min_ch = 1, > + .max_ch = 1, > + .simple_ch_prep_sm = true, > + .read_only_wordlength = true, > + }, { nit-pick: it's unu"
- Series 654926 patch 12899623: https://patchwork.kernel.org/project/alsa-devel/patch/20220629090644.67982-3-srinivas.kandagatla@linaro.org/
  - Topics: SoundWire, Objection/Correction; Requests: Fix SoundWire modeling
  - Comment excerpt: ">>> +static int wsa883x_update_status(struct sdw_slave *slave, >>> + enum sdw_slave_status status) >>> +{ >>> + struct wsa883x_priv *wsa883x = dev_get_drvdata(&slave->dev); >>> + >>> + if (status == SDW_SLAVE_ATTACHED && slave->dev_num > 0) >> >> do you actually need to test if s"
- Series 655429 patch 12901805: https://patchwork.kernel.org/project/alsa-devel/patch/20220630130023.9308-1-srinivas.kandagatla@linaro.org/
  - Topics: Runtime PM, SoundWire, Patch Structure; Requests: Fix Runtime PM flow, Fix SoundWire modeling
  - Comment excerpt: "On 6/30/22 08:00, Srinivas Kandagatla wrote: > Currently we do not check if SoundWire slave initialization timeout > expired before continuing to access its registers. > > Its possible that the registers are not accessible if timeout is > expired. Handle this by returning timeout"
- Series 733249 patch 13185869: https://patchwork.kernel.org/project/alsa-devel/patch/20230323164403.6654-4-srinivas.kandagatla@linaro.org/
  - Topics: Runtime PM, SoundWire; Requests: Fix SoundWire modeling
  - Comment excerpt: ">> +static int wsa883x_trigger(struct snd_pcm_substream *s, int cmd, >> + struct snd_soc_dai *dai) >> +{ >> + switch (cmd) { >> + case SNDRV_PCM_TRIGGER_START: >> + case SNDRV_PCM_TRIGGER_RESUME: >> + case SNDRV_PCM_TRIGGER_PAUSE_RELEASE: >> + wsa883x_digital_mute(dai, false, 0);"
- Series 804936 patch 13471452: https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/
  - Topics: SoundWire, Code Movement; Requests: Fix SoundWire modeling, Move code to proper file/layer
  - Comment excerpt: "> +int qcom_snd_sdw_startup(struct snd_pcm_substream *substream) > +{ > + struct snd_soc_pcm_runtime *rtd = substream->private_data; > + struct snd_soc_dai *cpu_dai = snd_soc_rtd_to_cpu(rtd, 0); > + struct sdw_stream_runtime *sruntime; > + struct snd_soc_dai *codec_dai; > + int r"
- Series 804936 patch 13471453: https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-2-krzysztof.kozlowski@linaro.org/
  - Topics: SoundWire; Requests: Fix SoundWire modeling
  - Comment excerpt: "On 11/28/23 10:56, Krzysztof Kozlowski wrote: > Currently the Qualcomm Soundwire controller in its DAI startup op > allocates the Soundwire stream runtime. This works fine for existing > designs, but has limitations for stream runtimes with multiple > controllers, like upcoming Q"
