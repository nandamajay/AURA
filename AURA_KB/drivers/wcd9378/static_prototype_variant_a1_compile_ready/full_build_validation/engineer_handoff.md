# WCD9378 A.1 Engineer Handoff

## PM Verdict

`COMPILE_READY_RFC_NOT_RUNTIME_READY`

The WCD9378 A.1 patch series now builds in a full arm64 linux-next kernel build and installs the WCD9378 modules. This is suitable to hand to a runtime/hardware engineer for board bring-up and evidence collection. It is not runtime-ready or upstream-ready yet.

## Build Inputs

- AURA patch directory: `AURA_KB/drivers/wcd9378/static_prototype_variant_a1_compile_ready/patches/`
- Kernel worktree used: `/local/mnt/workspace/aura_builds/wcd9378_a1_linux`
- Output directory used: `/local/mnt/workspace/aura_builds/wcd9378_a1_out`
- Kernel baseline: `ec039126b7fac4e3af35ebccaa7c6f9b6875ba81`
- Patched HEAD: `c34b5d1b7bfede66d560a5aed9bc8b354883c8d5`
- Toolchain: `aarch64-linux-gnu-gcc 11.4.0`

## Build Outputs

- Kernel image: `/local/mnt/workspace/aura_builds/wcd9378_a1_out/arch/arm64/boot/Image.gz`
- Module archive: `/local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules.cpio.gz`
- Codec module: `/local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir/lib/modules/7.1.0-rc7-next-20260611-00004-gc34b5d1b7bfe/kernel/sound/soc/codecs/snd-soc-wcd9378.ko`
- SoundWire module: `/local/mnt/workspace/aura_builds/wcd9378_a1_linux/modules_dir/lib/modules/7.1.0-rc7-next-20260611-00004-gc34b5d1b7bfe/kernel/sound/soc/codecs/snd-soc-wcd9378-sdw.ko`

## Checksums

- `Image.gz`: `7027d027532a6c301e5ff8d7c1f62456c11c0695ff2b37fb3a211af340f1f3e3`
- `modules.cpio.gz`: `8630d139a3c305b7d817b05809d10b516dd6da61c42acfd4f6d6c96753e63ca9`
- `snd-soc-wcd9378.ko`: `4a726a47f3bdcdfa854933a081485d6c796ea90bf6a37b89dc3d45793ba21b61`
- `snd-soc-wcd9378-sdw.ko`: `6dc32429ed1aaa5165079f02e0ff682ac961468a4ec0cda7a0cf41fcdeaed03c`

## What Passed

- Patch series applied with `git am`.
- `Image.gz dtbs modules` completed.
- `modules_install` completed.
- `modules.cpio.gz` was generated.
- `snd-soc-wcd9378.ko` and `snd-soc-wcd9378-sdw.ko` were installed.
- Installed WCD9378 modules are ELF64 little-endian AArch64 relocatable objects.

## Important Caveats

- `pahole` was not available, so BTF debug config was disabled for this build environment.
- This build does not validate runtime behavior.
- SoundWire paging, Class-H analog behavior, playback, capture, and reset/re-enumeration behavior remain fail-closed pending hardware evidence.

## Evidence To Collect On Board

- Boot dmesg for WCD9378 RX/TX SoundWire enumeration.
- SDW manufacturer ID, part ID, class/version/dev_num, modalias/sysfs identity.
- Register read/write traces for addresses above `0xffff`.
- Class-H/HPH/flyback register traces during headset playback enable/disable.
- Board DTS used for reset GPIO, supplies, RX/TX SWR pinctrl, SoundWire port mapping, and DAI links.
- Playback logs for headset path using `amixer` + `aplay`.
- Capture logs for AMIC1 using `amixer` + `arecord`.
- Any RX/TX slave detach/re-enumeration logs.
