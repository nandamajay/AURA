# Krzysztof Kozlowski Acceptance Model

## Evidence Strength
- Direct reviewer comments captured: **19**
- Confidence: **MEDIUM (78/100)**

## Observed Review Focus
- SoundWire: 11
- Code Movement: 8
- Objection/Correction: 7
- Patch Structure: 5
- DT: 3
- Runtime PM: 2
- Commit Message: 1
- General Review: 1

## Common Requested Changes
- Fix SoundWire modeling: 11
- General correction / clarification: 5
- Move code to proper file/layer: 5
- Adjust DT schema/binding: 3
- Fix Runtime PM flow: 2

## Acceptance Signals
- Patches tend to converge when reviewer-requested correctness/style updates are explicitly addressed in vN changelog and split cleanly when requested.
- Evidence basis: Patchwork comment records + accepted states in same series.

## Evidence Examples
- Series 693713 patch 13037726: https://patchwork.kernel.org/project/alsa-devel/patch/20221109163740.1158785-1-krzysztof.kozlowski@linaro.org/
  - Topics: Patch Structure; Requests: None-explicit
  - Comment excerpt: "On 09/11/2022 17:37, Krzysztof Kozlowski wrote: > The shutdown GPIO is active_low (sd_n), but this depends on actual board > layout. Linux drivers should only care about logical state, where high > (1) means shutdown and low (0) means do not shutdown. > > Invert the GPIO to match"
- Series 755223 patch 13271787: https://patchwork.kernel.org/project/alsa-devel/patch/20230608085023.141745-1-krzysztof.kozlowski@linaro.org/
  - Topics: DT, SoundWire, Commit Message; Requests: Adjust DT schema/binding, Fix SoundWire modeling
  - Comment excerpt: "On 08/06/2023 10:50, Krzysztof Kozlowski wrote: > Add binding for WSA8840/WSA8845/WSA8845H smart speaker amplifiers used > in Qualcomm QRD8550 board with SM8550 SoC. > > Signed-off-by: Krzysztof Kozlowski <krzysztof.kozlowski@linaro.org> > --- > .../bindings/sound/qcom,wsa8840.ya"
- Series 756050 patch 13275179: https://patchwork.kernel.org/project/alsa-devel/patch/20230611102657.74714-2-krzysztof.kozlowski@linaro.org/
  - Topics: Objection/Correction; Requests: None-explicit
  - Comment excerpt: "On 11/06/2023 13:57, Mark Brown wrote: > On Sun, Jun 11, 2023 at 12:26:57PM +0200, Krzysztof Kozlowski wrote: > >> +static struct reg_default wsa884x_defaults[] = { > >> + { WSA884X_CHIP_ID0, 0x00 }, >> + { WSA884X_CHIP_ID1, 0x00 }, >> + { WSA884X_CHIP_ID2, 0x04 }, >> + { WSA884X"
- Series 756224 patch 13276224: https://patchwork.kernel.org/project/alsa-devel/patch/20230612095716.118631-2-krzysztof.kozlowski@linaro.org/
  - Topics: SoundWire, Patch Structure, Objection/Correction; Requests: Fix SoundWire modeling
  - Comment excerpt: "On 12/06/2023 12:18, Srinivas Kandagatla wrote: > Thanks Krzyztof, > > few minor nits below. Please trim unrelated context - it's easy to miss a comment between huge quoted text. >> + >> +static const char * const wsa884x_dev_mode_text[] = { >> + "Speaker", "Receiver" >> +}; >> +"
- Series 804936 patch 13471453: https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-2-krzysztof.kozlowski@linaro.org/
  - Topics: SoundWire; Requests: Fix SoundWire modeling
  - Comment excerpt: "On 28/11/2023 17:56, Krzysztof Kozlowski wrote: > Currently the Qualcomm Soundwire controller in its DAI startup op > allocates the Soundwire stream runtime. This works fine for existing > designs, but has limitations for stream runtimes with multiple > controllers, like upcoming"
- Series 804936 patch 13471452: https://patchwork.kernel.org/project/alsa-devel/patch/20231128165638.757665-1-krzysztof.kozlowski@linaro.org/
  - Topics: SoundWire, Code Movement, Objection/Correction; Requests: Fix SoundWire modeling, Move code to proper file/layer
  - Comment excerpt: "On 28/11/2023 18:39, Pierre-Louis Bossart wrote: > >> +int qcom_snd_sdw_startup(struct snd_pcm_substream *substream) >> +{ >> + struct snd_soc_pcm_runtime *rtd = substream->private_data; >> + struct snd_soc_dai *cpu_dai = snd_soc_rtd_to_cpu(rtd, 0); >> + struct sdw_stream_runtime"
- Series 808754 patch 13487056: https://patchwork.kernel.org/project/alsa-devel/patch/20231211-topic-sm8x50-upstream-wsa884x-fix-plop-v1-1-0dc630a19172@linaro.org/
  - Topics: SoundWire, Code Movement; Requests: Fix SoundWire modeling, Move code to proper file/layer
  - Comment excerpt: "On 11/12/2023 12:40, Neil Armstrong wrote: > This fix is based on commit [1] fixing click and pop sounds during > SoundWire port start because PA is left unmuted. > > making use of new mute_unmute_on_trigger flag and removing unmute > at PA setup, removes the Click/Pop issue at S"
- Series 820841 patch 13535430: https://patchwork.kernel.org/project/alsa-devel/patch/20240129115216.96479-5-krzysztof.kozlowski@linaro.org/
  - Topics: DT, Patch Structure, Code Movement, Objection/Correction; Requests: Adjust DT schema/binding
  - Comment excerpt: "On 31/01/2024 09:57, Linus Walleij wrote: > Hi Krzysztof, > > something is odd with the addresses on this patch, because neither GPIO Nothing is odd - I use get_maintainers.pl which just don't print your names. I can add your addresses manually, no problem, but don't blame the co"
