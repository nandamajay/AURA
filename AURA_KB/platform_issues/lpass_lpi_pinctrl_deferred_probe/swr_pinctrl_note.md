# SoundWire Pinctrl Follow-up Note

This note covers SoundWire pinctrl references that must be added when the
SoundWire master nodes are introduced into `eliza.dtsi`. The upstream Eliza
DTS referenced for this patch does not yet contain `swr1`, `swr2`, or `swr3`,
so these references are intentionally documented here instead of emitted as a
patch hunk.

## Required Future Additions

### `swr1` — RX SoundWire master at `0x6ad0000`

When `swr1` is added to `eliza.dtsi`, include:

```dts
pinctrl-names = "default";
pinctrl-0 = <&rx_swr_active>;
```

Reference: `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/sm8750.dtsi:2434`.

### `swr2` — TX SoundWire master at `0x7630000`

When `swr2` is added to `eliza.dtsi`, include:

```dts
pinctrl-names = "default";
pinctrl-0 = <&tx_swr_active>;
```

Reference requested for this follow-up: `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/sm8750.dtsi:2387`.

### `swr3` — WSA SoundWire master at `0x6b10000`

When `swr3` is added to `eliza.dtsi`, include:

```dts
pinctrl-names = "default";
pinctrl-0 = <&wsa_swr_active>;
```

Reference: `track_b_corpora/linux-next/arch/arm64/boot/dts/qcom/sm8750.dtsi:2498`.

## Scope Boundary

This generated patch only adds the `gpr`/`q6prmcc` hierarchy and the
`lpass_tlmm` pinctrl node. It does not add SoundWire master nodes because they
are absent from the upstream Eliza DTS and are part of the later WCD9378
bring-up additions.
