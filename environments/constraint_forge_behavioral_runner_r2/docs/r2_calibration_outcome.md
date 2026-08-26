# R2 calibration outcome (2026-08-26)

## Ladder walk

- L1 (mutation 12 / write 4 / rounds 24): one MEDIUM dyad,
  seeds `constraint-forge/r2-calibration-v0`, sealed `completed` 24/24,
  774 live calls. Success fraction **4/24 = 0.167**.

SELECTION RULE APPLIED: first rung with fraction in [2/24, 12/24] -> L1
SELECTED AND FROZEN. No further rungs built or run. Overshoot/exhaustion
rules not triggered.

Note: the committed gatecheck's QUALIFICATION tiers printed FAIL on this
calibration dyad (Tier 3 wants >=6 successes); that evaluation is
meaningful only for qualification runs on fresh seeds. The calibration
question was band membership, and 4/24 is in-band. Recorded to prevent
confusion, not to relitigate gates.

## Frozen R2 substrate (for qualification)

mutation_budget=12, write_budget=4, max_rounds=24; everything else = R1.
Qualification seed prefix `constraint-forge/r2-qualification-v0` (fresh;
never used before this freeze). Gates: R1 tiers verbatim via committed
gatecheck. Then LOW one-shot iff MEDIUM passes.
