# Runtime PM Design (Blind v1)

## Design
- Enable autosuspend in probe.
- Mark device active post init.
- Use runtime suspend to cache-only regmap.
- Use runtime resume to re-enable regmap and sync.

## Safety requirements
- Guard against resume-time timeout/attach races.
- Return robust error paths before sync if transport not ready.
- Ensure DAI trigger/mute paths pair PM get/put calls correctly.
