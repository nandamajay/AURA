# Review Survival Rules v2

Evidence-backed rules extracted from reviewer-comment corpus expansion.

## Rule 1: Address objections with explicit vN delta notes
- Confidence: **HIGH_CONFIDENCE**
- Evidence count (topic-linked comments): **70**
- Rationale: Series with objection/correction comments converged when next revision explicitly implemented the requested fix and narrowed diff scope.
- Topics: Objection/Correction, Patch Structure
- Evidence: series 277321 patch 11510017 comment 23331733 (https://patchwork.kernel.org/project/alsa-devel/patch/20200425184657.121991-1-stephan@gerhold.net/)
- Evidence: series 350083 patch 11780381 comment 23624223 (https://patchwork.kernel.org/project/alsa-devel/patch/20200916111545.1.I4c3758817d94c433bafeac344a395e21ea6657e3@changeid/)
- Evidence: series 351647 patch 11785535 comment 23645509 (https://patchwork.kernel.org/project/alsa-devel/patch/1600448073-6709-1-git-send-email-srivasam@codeaurora.org/)

## Rule 2: Keep DT schema changes strictly schema-compliant and minimal
- Confidence: **MEDIUM_CONFIDENCE**
- Evidence count (topic-linked comments): **6**
- Rationale: DT review comments repeatedly flag schema wording/properties consistency; accepted revisions align schema with standard expectations.
- Topics: DT
- Evidence: series 277321 patch 11510017 comment 23331733 (https://patchwork.kernel.org/project/alsa-devel/patch/20200425184657.121991-1-stephan@gerhold.net/)
- Evidence: series 694081 patch 13038802 comment 25086581 (https://patchwork.kernel.org/project/alsa-devel/patch/20221110133512.478831-1-krzysztof.kozlowski@linaro.org/)
- Evidence: series 755223 patch 13271787 comment 25373072 (https://patchwork.kernel.org/project/alsa-devel/patch/20230608085023.141745-1-krzysztof.kozlowski@linaro.org/)

## Rule 3: Runtime PM sequencing issues are review blockers
- Confidence: **HIGH_CONFIDENCE**
- Evidence count (topic-linked comments): **12**
- Rationale: Comments involving pm_runtime/autosuspend/resume semantics correlate with corrective iterations before acceptance.
- Topics: Runtime PM
- Evidence: series 366535 patch 11843861 comment 23720097 (https://patchwork.kernel.org/project/alsa-devel/patch/1603098363-9251-1-git-send-email-srivasam@codeaurora.org/)
- Evidence: series 616303 patch 12753616 comment 24747183 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-2-srinivas.kandagatla@linaro.org/)
- Evidence: series 616303 patch 12753626 comment 24747312 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-10-srinivas.kandagatla@linaro.org/)

## Rule 4: SoundWire modeling details require precise integration semantics
- Confidence: **HIGH_CONFIDENCE**
- Evidence count (topic-linked comments): **45**
- Rationale: SoundWire-related review comments cluster around SDW/SWR modeling correctness and lifecycle behavior.
- Topics: SoundWire
- Evidence: series 476859 patch 12238055 comment 24168653 (https://patchwork.kernel.org/project/alsa-devel/patch/20210504125909.16108-1-srinivas.kandagatla@linaro.org/)
- Evidence: series 500597 patch 12321535 comment 24251169 (https://patchwork.kernel.org/project/alsa-devel/patch/20210615132829.23067-1-srinivas.kandagatla@linaro.org/)
- Evidence: series 514801 patch 12374047 comment 24311489 (https://patchwork.kernel.org/project/alsa-devel/patch/20210713140417.23693-1-srinivas.kandagatla@linaro.org/)

## Rule 5: Patch organization affects review velocity
- Confidence: **HIGH_CONFIDENCE**
- Evidence count (topic-linked comments): **55**
- Rationale: Requests to split/refactor patch series appear in accepted Qualcomm audio series and improve reviewer tractability.
- Topics: Patch Structure
- Evidence: series 277321 patch 11510017 comment 23331733 (https://patchwork.kernel.org/project/alsa-devel/patch/20200425184657.121991-1-stephan@gerhold.net/)
- Evidence: series 350083 patch 11780381 comment 23624223 (https://patchwork.kernel.org/project/alsa-devel/patch/20200916111545.1.I4c3758817d94c433bafeac344a395e21ea6657e3@changeid/)
- Evidence: series 351647 patch 11785535 comment 23645509 (https://patchwork.kernel.org/project/alsa-devel/patch/1600448073-6709-1-git-send-email-srivasam@codeaurora.org/)

## Rule 6: Commit message quality impacts acceptance
- Confidence: **MEDIUM_CONFIDENCE**
- Evidence count (topic-linked comments): **6**
- Rationale: Commit message/subject/changelog improvements are requested alongside technical fixes in converged series.
- Topics: Commit Message
- Evidence: series 371353 patch 11860083 comment 23717423 (https://patchwork.kernel.org/project/alsa-devel/patch/1603798474-4897-1-git-send-email-srivasam@codeaurora.org/)
- Evidence: series 616303 patch 12753626 comment 24747206 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-10-srinivas.kandagatla@linaro.org/)
- Evidence: series 616303 patch 12753626 comment 24747312 (https://patchwork.kernel.org/project/alsa-devel/patch/20220221131037.8809-10-srinivas.kandagatla@linaro.org/)

