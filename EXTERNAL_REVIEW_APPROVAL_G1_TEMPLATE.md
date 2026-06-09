# TEMPLATE — External Review Approval (G1)

**This file is a TEMPLATE only. It does NOT authorize execution.**

Copy to `EXTERNAL_REVIEW_APPROVAL_G1_READ_ONLY_CHALLENGER_COST_EVIDENCE.md` only after external controller review.

---

## Phase authorized (if approved)

`G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION`

## Scope (read-only evidence only)

- Generate variant-specific turnover and cost artefacts for `MOM_63_TOP12`
- Document identical comparison logic for Champion and M1
- Prepare Cost-Stress, DSR, PBO/CSCV, and Robustness evidence packages
- **No** Shadow, Paper, Promotion, Champion change, or Real-Money actions

## Explicitly NOT authorized by this template

- Backtest execution (unless separately listed in approved scope)
- Shadow monitoring activation
- Paper monitoring activation
- Promotion execution
- Champion change
- Real-money execution
- EXE build or EXE execution
- Operative jobs, replay, broker connectivity

## Required verification before execution

- [ ] Document hash registered in `control/vision_automation/review_registry/review_registry.json`
- [ ] Phase catalog permits `G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION`
- [ ] `control/authorization/current_authorization_status.json` shows no source conflict
- [ ] G0 remediation PASS with protected artefact hashes unchanged
- [ ] Evidence gates pass for requested read-only scope

## Review decision

- [ ] APPROVED — limited read-only challenger cost/statistics evidence preparation
- [ ] REJECTED — hold; no execution

Reviewer signature / date: ____________________

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
