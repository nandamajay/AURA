# Transport Runtime Limitations

- Live endpoint connectivity was not validated in this pass.
- Prompt synchronization quality depends on board shell prompt stability.
- Serial exit-code extraction relies on shell marker parsing.
- pyserial must be present on Windows host.
- Persistent SSH/adb transport behavior is out of this phase scope.
