# RB3 Audio Route Knowledge Graph

## Graph domains
- FE/BE relationships
- mixer dependency edges
- codec routes
- SoundWire dependencies
- overlay inheritance
- playback topology endpoint

## Source correlation
- static: DTS/DTSI (`qcom,audio-routing`, dai-links, codec nodes)
- runtime: PCM/DAPM/mixer/dmesg correlation signatures

## Purpose
- deterministic route planning
- reusable playback/capture topology memory
- downstream runtime evidence fed back into upstream planning memory
