# Base WSA/VA/DMIC Patch Impact Note

`base_wsa_va_dmic.patch` changes the patch strategy.

## Finding

The base patch already adds `lpass_tlmm: pinctrl@7760000` to `eliza.dtsi` and
adds board-level WSA/VA/DMIC pinctrl states through EVK/MTP overlays. It also
adds WSA and VA macro nodes and the WSA SoundWire node.

However, the base patch does **not** add the `gpr` hierarchy under
`remoteproc_adsp` and does **not** define `q6prmcc: clock-controller`.

## Consequence

If `base_wsa_va_dmic.patch` has already been applied, the original generated
`eliza_lpass_lpi_fix.patch` is too broad because it also adds `lpass_tlmm` and
will conflict with the base patch.

Use `eliza_gpr_q6prmcc_addendum_for_base_wsa_va_dmic.patch` instead. That
addendum only adds the missing `gpr -> q6apm/q6prm -> q6prmcc` hierarchy and
leaves the base patch's LPASS TLMM node and board pinctrl states untouched.

## Remaining Board Checks

- Confirm `q6prmcc` registers and supplies the LPASS clock consumers.
- Confirm `7760000.pinctrl` no longer reports `Failed to get clk 'core'`.
- Confirm VA/WSA/DMIC probe order after the GPR/Q6PRM provider appears.
- Do not treat this as proof that end-to-end audio works.
