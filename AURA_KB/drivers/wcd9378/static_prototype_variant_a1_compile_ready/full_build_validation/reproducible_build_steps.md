# WCD9378 A.1 Reproducible Full Build Steps

## Purpose

Use these steps to reproduce the WCD9378 A.1 full arm64 kernel build, install modules, and package `modules.cpio.gz` for engineer handoff.

## PM Classification

`COMPILE_READY_RFC_NOT_RUNTIME_READY`

This build proves that the WCD9378 A.1 patch series applies and compiles. It does not prove playback, capture, SoundWire paging, Class-H behavior, board DTS correctness, or upstream readiness.

## Assumptions

- AURA repo: `/local/mnt/workspace/AURA_V1_upstream`
- AURA branch: `aura_upstream_learning`
- Kernel source: `track_b_corpora/linux-next`
- Kernel baseline: `ec039126b7fac4e3af35ebccaa7c6f9b6875ba81`
- Build worktree: `/local/mnt/workspace/aura_builds/wcd9378_a1_linux`
- Build output: `/local/mnt/workspace/aura_builds/wcd9378_a1_out`
- Toolchain prefix: `aarch64-linux-gnu-`

## 1. Start From AURA Repo

```bash
cd /local/mnt/workspace/AURA_V1_upstream
git checkout aura_upstream_learning
git status --short
```

Expected: clean or only intentional local changes.

## 2. Create Clean Kernel Worktree

```bash
mkdir -p /local/mnt/workspace/aura_builds

git -C track_b_corpora/linux-next worktree add --detach \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux \
  ec039126b7fac4e3af35ebccaa7c6f9b6875ba81
```

If the worktree already exists and you want a fresh rebuild, remove it safely first:

```bash
git -C track_b_corpora/linux-next worktree remove --force \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux

rm -rf /local/mnt/workspace/aura_builds/wcd9378_a1_out
```

Then rerun the worktree creation command.

## 3. Apply WCD9378 A.1 Patch Series

```bash
cd /local/mnt/workspace/aura_builds/wcd9378_a1_linux

git am /local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/patches/*.patch

git log --oneline -5
```

Expected top patch stack:

```text
ASoC: codecs: wire WCD9378 Kconfig/Makefile entries (RFC static prototype)
ASoC: codecs: add WCD9378 codec scaffold (RFC static prototype)
ASoC: codecs: add WCD9378 SoundWire scaffold (RFC static prototype)
ASoC: codecs: add WCD9378 shared header (RFC static prototype)
```

## 4. Prepare Build Directories

```bash
mkdir -p modules_dir firmwares_dir test_utils logs
mkdir -p /local/mnt/workspace/aura_builds/wcd9378_a1_out
```

## 5. Export Build Environment

```bash
export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-
```

Verify toolchain:

```bash
which aarch64-linux-gnu-gcc
aarch64-linux-gnu-gcc --version | head -1
```

## 6. Generate Defconfig

```bash
make O=/local/mnt/workspace/aura_builds/wcd9378_a1_out \
  -j$(nproc) defconfig 2>&1 | tee logs/01_defconfig.log
```

## 7. Enable Required WCD9378 Configs

```bash
./scripts/config --file /local/mnt/workspace/aura_builds/wcd9378_a1_out/.config \
  -e SOUNDWIRE \
  -e REGMAP_SOUNDWIRE \
  -e REGMAP_IRQ \
  -e SND_SOC \
  -e SND_SOC_WCD_CLASSH \
  -e SND_SOC_WCD_COMMON \
  -e SND_SOC_WCD_MBHC \
  -e SND_SOC_WCD9378 \
  -e SND_SOC_WCD9378_SDW \
  -d DEBUG_INFO_BTF \
  -d DEBUG_INFO_BTF_MODULES 2>&1 | tee logs/02_scripts_config.log
```

`DEBUG_INFO_BTF` and `DEBUG_INFO_BTF_MODULES` are disabled here because the validation machine did not have `pahole`. If your build machine has `pahole`, you may choose to keep BTF enabled.

## 8. Finalize Config

```bash
make O=/local/mnt/workspace/aura_builds/wcd9378_a1_out \
  -j$(nproc) olddefconfig 2>&1 | tee logs/03_olddefconfig.log
```

Verify config:

```bash
grep -nE '^(CONFIG_SND_SOC_WCD9378|CONFIG_SND_SOC_WCD9378_SDW|CONFIG_SOUNDWIRE|CONFIG_REGMAP_SOUNDWIRE|CONFIG_SOUNDWIRE_QCOM)' \
  /local/mnt/workspace/aura_builds/wcd9378_a1_out/.config
```

Expected important entries:

```text
CONFIG_REGMAP_SOUNDWIRE=m
CONFIG_SND_SOC_WCD9378=m
CONFIG_SND_SOC_WCD9378_SDW=m
CONFIG_SOUNDWIRE=m
CONFIG_SOUNDWIRE_QCOM=m
```

## 9. Build Kernel, DTBs, and Modules

```bash
make O=/local/mnt/workspace/aura_builds/wcd9378_a1_out \
  -j$(nproc) Image.gz dtbs modules 2>&1 | tee logs/04_full_build.log
```

## 10. Install Modules

```bash
make O=/local/mnt/workspace/aura_builds/wcd9378_a1_out \
  -j$(nproc) modules_install \
  INSTALL_MOD_PATH=/local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir \
  INSTALL_MOD_STRIP=1 2>&1 | tee logs/05_modules_install.log
```

## 11. Pack Modules

```bash
cd /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir

find . | cpio -o -H newc | gzip -9 > ../modules.cpio.gz

cd /local/mnt/workspace/aura_builds/wcd9378_a1_linux
```

## 12. Verify WCD9378 Build Evidence

```bash
grep -nE 'wcd9378|snd-soc-wcd9378' logs/04_full_build.log logs/05_modules_install.log

find modules_dir -name '*wcd9378*.ko' -print -exec ls -lh {} \;

aarch64-linux-gnu-readelf -h \
  modules_dir/lib/modules/*/kernel/sound/soc/codecs/snd-soc-wcd9378.ko | head -20

aarch64-linux-gnu-readelf -h \
  modules_dir/lib/modules/*/kernel/sound/soc/codecs/snd-soc-wcd9378-sdw.ko | head -20
```

Expected evidence includes:

```text
CC [M]  sound/soc/codecs/wcd9378.o
CC [M]  sound/soc/codecs/wcd9378-sdw.o
LD [M]  sound/soc/codecs/snd-soc-wcd9378.ko
LD [M]  sound/soc/codecs/snd-soc-wcd9378-sdw.ko
INSTALL .../kernel/sound/soc/codecs/snd-soc-wcd9378.ko
INSTALL .../kernel/sound/soc/codecs/snd-soc-wcd9378-sdw.ko
```

## 13. List Final Handoff Artifacts

```bash
ls -lh \
  /local/mnt/workspace/aura_builds/wcd9378_a1_out/arch/arm64/boot/Image.gz \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules.cpio.gz \
  /local/mnt/workspace/aura_builds/wcd9378_a1_out/Module.symvers

find /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir \
  -name '*wcd9378*.ko' -print
```

Give these to the engineer:

```text
/local/mnt/workspace/aura_builds/wcd9378_a1_out/arch/arm64/boot/Image.gz
/local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules.cpio.gz
/local/mnt/workspace/AURA_V1_upstream/AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/patches/
```

## 14. Optional Checksums

```bash
sha256sum \
  /local/mnt/workspace/aura_builds/wcd9378_a1_out/arch/arm64/boot/Image.gz \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules.cpio.gz \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir/lib/modules/*/kernel/sound/soc/codecs/snd-soc-wcd9378.ko \
  /local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir/lib/modules/*/kernel/sound/soc/codecs/snd-soc-wcd9378-sdw.ko
```

## Runtime Evidence Still Required

Ask the runtime/hardware engineer to collect:

- Boot dmesg for WCD9378 RX/TX SoundWire enumeration.
- SDW manufacturer ID, part ID, class/version/dev_num, modalias/sysfs identity.
- Register read/write traces for addresses above `0xffff`.
- Class-H/HPH/flyback register traces during headset playback enable/disable.
- Board DTS used for reset GPIO, supplies, RX/TX SWR pinctrl, SoundWire port mapping, and DAI links.
- Playback logs using `amixer` + `aplay`.
- Capture logs using `amixer` + `arecord`.
- Any RX/TX slave detach/re-enumeration logs.

## Final PM Note

If this build fails in another environment, fix only compile/static issues from the build log. Do not add runtime workarounds, SoundWire controller behavior changes, LPASS macro behavior changes, or reset-in-`hw_params()` logic without hardware evidence and an explicit upstreamability review.
