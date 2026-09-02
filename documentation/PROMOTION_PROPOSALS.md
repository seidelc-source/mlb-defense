# Promotion Proposals

> Candidate methodological lessons from this project, proposed for the central `principal-ds` skill. Proposals are NEVER applied automatically — the central methodology changes only when the human explicitly approves a proposal and asks for it to be applied.
>
> A project fact ("dataset X has a broken aggregation") stays here. Only the generalized lesson ("reconcile derived aggregates against source-level totals") is promotable — and that example is already central.

_No promotion proposals yet._

Candidate lesson observed during integration (not yet proposed — appears already covered by the central baseline-first / evidence-labeling contract): when a system is a **deterministic heuristic with metric-like outputs** (e.g. names like `predicted_oaa_delta`, `predicted_hit_pct`), treat those outputs as UNVALIDATED until compared to realized outcomes, and audit whether the output's *name* implies a calibrated quantity it does not actually represent. If a distilled, generalizable version proves reusable across projects, formalize it here before proposing.
