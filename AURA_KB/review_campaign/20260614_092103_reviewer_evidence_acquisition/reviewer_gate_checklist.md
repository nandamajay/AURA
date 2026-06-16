# Reviewer Gate Checklist

Use this gate before sending Qualcomm audio patch series.

- [ ] All reviewer-raised objections from prior family history are explicitly addressed in cover letter changelog (vN delta).
- [ ] Patch split is reviewable and bisect-safe; DT/schema patch separated from driver logic where appropriate.
- [ ] DT schema passes strict validation and matches binding conventions (property naming, constraints, examples).
- [ ] Runtime PM lifecycle (probe/resume/suspend/error-path) is internally consistent and justified in commit text.
- [ ] SoundWire lifecycle and port/stream semantics are documented and aligned with existing upstream model.
- [ ] Commit messages describe problem and behavior change, not only implementation detail.
- [ ] Code movement/refactoring requests from prior similar series are preemptively applied (layer boundaries clear).
- [ ] Series includes explicit testing/validation note for key runtime behaviors touched.
- [ ] Cover letter identifies what changed since previous revision using reviewer-specific closure notes.

## Confidence Gate
- If two or more checklist items are unresolved for a targeted reviewer area, classify as **NOT_READY_FOR_SUBMISSION**.
- If all items are satisfied with evidence links, classify as **REVIEW_READY**.
