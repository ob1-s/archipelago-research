# Constraint Forge V0 — Final Analysis Report
**Cohorts:** `constraint-forge-formation-cohort-luna-low-v0` / `…luna-medium-v0`
**Freeze commits:** `c01fb96` (policy) → `117bace` (`--only-dyad` execution fix); plans identical across arms
**Model:** `gpt-5.6-luna` via loopback openai-oauth proxy · **Date sealed:** 2026-08-24

---

## 1. Pre-declared verdict

**V0 FAILS its promotion gate.** Gate required ≥8 of 12 dyads reaching ≥70%
success over the final eight non-occluded jobs. Achieved:

| arm | competent dyads | completed dyads | max final-eight mean |
|---|---|---|---|
| LOW | **0** | 4 | 0.12 |
| MEDIUM | **0** | 7 | 0.25 |

Per spec §11: stop and preserve; any repair becomes separately-named V1.
This report is the preserved result.

## 2. Headline descriptive findings

- **Spontaneous formations occurred at all**: 3 (LOW) vs **15** (MEDIUM)
  formation events across ~19 completed-dyad equivalents.
- MEDIUM formed in **6 of 7** completed dyads; LOW in 2 of 4.
- On the four clean matched pairs (dyads 0–3): **MEDIUM ≥ LOW in every pair**
  (per-pair: 2–0, 2–1, 2–0, 2–2). *n=4 is a strong descriptive signal only —
  not confirmatory evidence of an effort effect.*
- Per-job formation rate on completed dyads: MEDIUM ≈ 8.3%, LOW ≈ 3.1%.

## 3. Where formations happened (developmental structure)

- Formations cluster **late and in probe blocks**: MEDIUM probe-block means
  reach 0.33 in four dyads while ordinary-block means stay ≤0.14 everywhere.
- **MEDIUM-05 is the standout**: five formations spanning *all three job kinds*
  (faults 5 & 7, ordinary 8, probes 18 & 21) within one sequence — evidence of
  a generalized routine forming mid-sequence rather than item-specific luck.
- All LOW formations were late (jobs 15, 16, 22).
- Solves consistently used MORE rounds than failures (9–14 vs 8), i.e., success
  came from conflict-repair over extra rounds, not faster play.

## 4. Coordination taxonomy (completed dyads)

| pattern | LOW | MEDIUM |
|---|---|---|
| turf-war rounds (same item, clashing targets) | 175 | 270 |
| agreeing rounds | 31 | 67 |
| echo moves (actor repeats partner's previous action) | 51 | 106 |

Conflict is the default state; MEDIUM converts more of it into agreement and
shows ~2× the leader–follower echoing. Observed win-modes: swap-via-neutral-
placement repair, and strict turn-taking (Y mirroring X one step behind).

## 5. Memory (film) structure

- Films retained: LOW 133 (6 dyads), MEDIUM 228 (9 dyads).
- Filmed sources **precede** first formation in every forming dyad
  (LOW 34 pre / 0 post; MEDIUM 87 pre / 21 post — the "post" set is filming of
  the formation jobs themselves). Ordering is consistent with
  retain→later-form development; causality unproven at n=this.

## 6. Fault-block recovery

Post-fault ordinary block (jobs 8–17): LOW 2/40 = 5.0%, MEDIUM 2/70 = 2.9% —
neither arm recovered competence after occlusion. The lone counterexample is
again MEDIUM-05 (formed ON fault jobs).

## 7. Cost accounting (executed dyads, all statuses)

| arm | native calls | wall time | prompt toks | completion toks |
|---|---|---|---|---|
| LOW | 2,742 | 11.2 h | 27.0 M | 0.58 M |
| MEDIUM | 4,544 | 17.2 h | 45.5 M | 1.61 M |

## 8. Incident appendix

1. **Upstream outages** (proxy → provider "fetch failed"): killed LOW-04
   (job 9/24), MEDIUM-04 (10/24), LOW-05 (1 call), MEDIUM-06 (6/24),
   MEDIUM-08 (1/24), MEDIUM-09 (1/24), MEDIUM-10 (0 calls, resume attempt).
   Aborts are declared outcome class; retry chains recorded.
2. **Silent driver deaths** (~21:15–21:48): six driver processes died without
   traceback (suspected OOM on 13 GB host; unconfirmed). Orphaned launchers
   completed their work honestly; all evidence sha256-verifies against
   manifests.
3. **Bookkeeping gap**: MEDIUM-08's manifest row lost to the chaos; sealed
   aborted-evidence preserved at `qual_artifacts/orphan-dyad-08-medium-aborted.json`.
4. **Tooling finding**: frozen code halts an arm on a trailing streak of 3
   aborts regardless of prior completions, while the freeze-record text says
   "3 aborted AND none completed." LOW was ended by the stricter code rule
   (dyads 7–11 unexecuted). No frozen package code was modified mid-experiment;
   discrepancy logged for V1.
5. Driver row-format parsing bug caused one false-abort cascade early
   (pair 0 completed safely regardless).

## 9. What V1 should change (design implications)

1. **Gate calibration**: with baseline formation rates ~3–8% of jobs, a 70%
   final-eight gate demands near-perfect competence. Either raise per-dyad
   episode count, add within-sequence curriculum, or gate on trajectory slope.
2. **Probe-vs-ordinary gap**: agents form routines that pass probes but not
   standard jobs — investigate what differs (occlusion? target configs?) as
   the primary V1 lever.
3. **Memory lever**: retention universally precedes formation; V1 should make
   film curation manipulable (e.g., forced-forget arms) to test causality.
4. **Effort factor**: keep LOW/MEDIUM pairing but power it properly
   (≥12 completed dyads/arm; tonight's infra budget must assume ~30% attrition).
5. **Infra hardening**: dedicated process supervisor with memory headroom,
   manifest-row reconciliation command, upstream health-gate before dispatch.

*All inputs are sealed, hash-chained evidence under
`cohort_artifacts/constraint-forge-formation-cohort-luna-{low,medium}-v0/`.*
