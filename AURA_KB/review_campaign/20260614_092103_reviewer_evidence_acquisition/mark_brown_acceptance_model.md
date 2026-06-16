# Mark Brown Acceptance Model

## Evidence Strength
- Direct reviewer comments captured: **61**
- Confidence: **HIGH (90/100)**

## Observed Review Focus
- Patch Structure: 47
- SoundWire: 22
- Code Movement: 7
- Runtime PM: 5
- General Review: 5
- Commit Message: 4
- Objection/Correction: 4
- DT: 3
- DAPM: 2

## Common Requested Changes
- General correction / clarification: 34
- Fix SoundWire modeling: 22
- Move code to proper file/layer: 7
- Adjust DT schema/binding: 3
- Improve commit message: 2
- Fix Runtime PM flow: 1

## Acceptance Signals
- Patches tend to converge when reviewer-requested correctness/style updates are explicitly addressed in vN changelog and split cleanly when requested.
- Evidence basis: Patchwork comment records + accepted states in same series.

## Evidence Examples
- Series 277321 patch 11510017: https://patchwork.kernel.org/project/alsa-devel/patch/20200425184657.121991-1-stephan@gerhold.net/
  - Topics: DT, Patch Structure; Requests: Adjust DT schema/binding
  - Comment excerpt: "On Sat, 25 Apr 2020 20:46:56 +0200, Stephan Gerhold wrote: > The lpass-cpu driver now allows configuring the MI2S SD lines > by defining subnodes for one of the DAIs. > > Document this in the device tree bindings. > > Signed-off-by: Stephan Gerhold <stephan@gerhold.net> > > [...]"
- Series 350083 patch 11780381: https://patchwork.kernel.org/project/alsa-devel/patch/20200916111545.1.I4c3758817d94c433bafeac344a395e21ea6657e3@changeid/
  - Topics: Patch Structure; Requests: None-explicit
  - Comment excerpt: "On Wed, 16 Sep 2020 11:15:55 -0700, Douglas Anderson wrote: > The lpass-sc7180 driver can be built as a module but is lacking a > MODULE_DEVICE_TABLE. This means it won't auto-load. Fix this > oversight. Applied to https://git.kernel.org/pub/scm/linux/kernel/git/broonie/sound.git"
- Series 351647 patch 11785535: https://patchwork.kernel.org/project/alsa-devel/patch/1600448073-6709-1-git-send-email-srivasam@codeaurora.org/
  - Topics: Patch Structure, Code Movement; Requests: Move code to proper file/layer
  - Comment excerpt: "On Fri, 18 Sep 2020 22:24:33 +0530, Srinivasa Rao Mandadapu wrote: > Update lpass-cpu.c to enable I2S BCLK and LRCLK together. > Remove BCLK enable in lpass_cpu_daiops_startup and > add in lpass_cpu_daiops_trigger API. Applied to https://git.kernel.org/pub/scm/linux/kernel/git/br"
- Series 371353 patch 11860083: https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/
  - Topics: Patch Structure, Commit Message; Requests: None-explicit
  - Comment excerpt: "On Tue, Oct 27, 2020 at 05:04:34PM +0530, Srinivasa Rao Mandadapu wrote: > Update SC7180 lpass_variant structure with proper I2S bitwidth > field bit positions, as bitwidth denotes 0 to 1 bits, > but previously used only 0 bit. To repeat my previous feedback: | Please submit patc"
- Series 371353 patch 11860083: https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/
  - Topics: Patch Structure; Requests: None-explicit
  - Comment excerpt: "On Tue, Oct 27, 2020 at 05:04:34PM +0530, Srinivasa Rao Mandadapu wrote: > Fixes: cba62c8b49be ("ASoC: qcom: Add support for SC7180 lpass variant") This commit is actually Merge series "ASoC: qcom: Add support for SC7180 lpass variant" from Rohit kumar <rohitkr@codeaurora.org>: w"
- Series 366535 patch 11843861: https://patchwork.kernel.org/project/alsa-devel/patch/1603098363-9251-1-git-send-email-srivasam@codeaurora.org/
  - Topics: Runtime PM, Patch Structure; Requests: None-explicit
  - Comment excerpt: "On Mon, 19 Oct 2020 14:36:03 +0530, Srinivasa Rao Mandadapu wrote: > Disable MI2S bit clock from PAUSE/STOP/SUSPEND usecase instead of > shutdown time. Acheive this by invoking clk_disable API from > cpu daiops trigger instead of cpu daiops shutdown. > Change non-atomic API "clk_"
- Series 371353 patch 11860083: https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/
  - Topics: Patch Structure; Requests: None-explicit
  - Comment excerpt: "On Tue, 27 Oct 2020 17:04:34 +0530, Srinivasa Rao Mandadapu wrote: > Update SC7180 lpass_variant structure with proper I2S bitwidth > field bit positions, as bitwidth denotes 0 to 1 bits, > but previously used only 0 bit. Applied to https://git.kernel.org/pub/scm/linux/kernel/git"
- Series 500597 patch 12321535: https://patchwork.kernel.org/project/alsa-devel/patch/20210615132829.23067-1-srinivas.kandagatla@linaro.org/
  - Topics: SoundWire, Patch Structure, Code Movement; Requests: Fix SoundWire modeling, Move code to proper file/layer
  - Comment excerpt: "On Tue, 15 Jun 2021 14:28:29 +0100, Srinivas Kandagatla wrote: > For some reason we ended up with cyclic dependency between snd_soc_wcd938x > and snd_soc_wcd938x_sdw modules. > > Remove this cyclic dependency by handling them in respective modules. > Without this below error is r"
