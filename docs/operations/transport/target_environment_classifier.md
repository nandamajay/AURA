# Target Environment Classifier

## Inputs
- `uname -a`
- `cat /proc/version`
- `cat /proc/asound/cards`
- `cat /proc/cpuinfo`
- command stderr/stdout signatures (`not found`, shell errors)
- kernel/platform markers (`qemu`, `virtio`, `qcs`, `rb3`, `qualcomm`, `ubuntu`, `yocto`)

## Outputs
- `primary_environment`
- `detected_environments` (multi-label)
- confidence (`LOW|MEDIUM|HIGH`)
- evidence markers preserved as lists

## Supported labels
- Android
- Embedded Linux
- QEMU
- Yocto
- Qualcomm Linux
- Ubuntu

## Fail-closed behavior
- Missing probes do not imply unsupported platform certainty.
- Unknown markers remain `UNKNOWN`, not inferred.
