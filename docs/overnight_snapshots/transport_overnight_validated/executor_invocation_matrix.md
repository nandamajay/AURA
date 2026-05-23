# Executor Invocation Matrix

| Command | Normalized | Executor Invocation | Expected Mode |
|---|---|---|---|
| getprop ro.build.fingerprint | getprop ro.build.fingerprint | adb.exe -s <serial> shell getprop ro.build.fingerprint | adb_shell |
| cat /proc/version | cat /proc/version | adb.exe -s <serial> shell cat /proc/version | adb_shell |
| cat /proc/asound/cards | cat /proc/asound/cards | adb.exe -s <serial> shell cat /proc/asound/cards | adb_shell |
| echo AURA_BRIDGE_PING | echo AURA_BRIDGE_PING | adb.exe -s <serial> shell echo AURA_BRIDGE_PING | adb_shell |
| AURA_PLAYBACK_APLAY | AURA_PLAYBACK_APLAY <(plug)hw:x,y> <target_path> | adb.exe -s <serial> shell aplay -D <(plug)hw:x,y> <target_path> | adb_shell |
| AURA_AMIXER_NAME_SET | AURA_AMIXER_NAME_SET <base64url(control_name)> <value> | adb.exe -s <serial> shell amixer -c 0 cset iface=MIXER,name='<decoded>' '<value>' | adb_shell |

## Required response fields
- `executor_command_trace[].normalized_command`
- `executor_command_trace[].raw_executor_invocation`
- `executor_command_trace[].exit_code`
- `raw_executor_invocation[]`
- `transport_expansion_trace[]`
