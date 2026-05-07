# Confluence Research

This folder is the shared research surface for Codex and Claude after the first Phase 4 NQ seed-pack sweep.

The working thesis is that published strategies should not be copied directly. Papers, ICT videos, and discretionary material are feature sources. The next edge, if it exists, should come from mechanically defined confluences that approximate informed discretion:

- liquidity sweep and reclaim
- displacement / fair value gap
- break of structure
- order-block retest
- session / killzone
- VWAP stretch or reversion
- trend and volatility regime
- compression / expansion
- order-flow imbalance, queue imbalance, absorption, delta, and depth features where Rithmic/Quantower data makes them available

## Folder Map

- `USER_UPLOAD_STEPS.txt` — instructions for Georg.
- `PAPER_LEADS.md` — first research leads to inspect.
- `INGESTION_LOG.md` — append one row per uploaded/processed source.
- `raw_materials/` — ignored by Git; put videos, PDFs, audio, and private notes here.
- `processed/` — compact artifacts agents can read without loading raw videos.
- `specs/` — candidate strategy specs before Pine/Python implementation.

## Rules

- Do not commit raw course/video/PDF material.
- Do not promote a confluence because it looks good full-sample.
- Every concept must become a boolean or numeric feature.
- Every candidate spec needs an ablation plan and predeclared IS/OOS split before testing.
- `P4_Sweep_Reclaim_v0 M3` is the current benchmark distribution to beat.
