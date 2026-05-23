# Transport Expansion Rules

## Boundary contract
- Linux payload command is canonical target command.
- Windows worker expands command exactly once.

## Expansion
- canonical: `<normalized_command>`
- executor invocation: `adb.exe -s <serial> shell <normalized_command>`
- disallow nested expansion (`adb shell adb shell ...`)
- governed wrapper expansion:
  - `AURA_ADB_PUSH` -> `adb.exe push ...`
  - `AURA_AMIXER_NAME_SET <base64url(name)> <value>` -> `adb.exe shell amixer -c 0 cset iface=MIXER,name='<decoded_name>' '<value>'`

## Trace fields
- request: `command_entries[].normalized_command`
- response: `transport_expansion_trace[]`
- response: `raw_executor_invocation[]`

## Fail-closed outcomes
- malformed envelope => `INVALID`
- expansion boundary violation => `REJECTED`
- disconnected adb/runtime => `UNKNOWN`
