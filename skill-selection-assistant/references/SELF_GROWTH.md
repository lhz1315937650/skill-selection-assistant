# Feedback And Self-Growth Reference

Read this reference only for feedback analysis, selection-memory maintenance, taxonomy improvements, or new-skill planning.

## Privacy

Do not store raw user queries by default. Record outcome, selected skill, and route labels; store shortened raw queries only with `--store-query` after the user accepts local retention.

## Bounded Memory

- positive selections may boost a skill only within a compatible route
- rejection and setup failure may reduce its compatible-route score
- root-level routing must not inherit route-specific memory
- clamp accumulated scores so feedback cannot permanently dominate semantic fit

## Assisted Growth

Self-growth is review-assisted, not uncontrolled rule mutation.

1. Aggregate missed, rejected, setup-failed, overlap, and new-skill-needed outcomes.
2. Identify recurring gaps and oversized routes.
3. Propose rule aliases, category splits, merges, or new skills.
4. Show the proposed change and expected effect.
5. Apply only after user approval.
6. Rebuild the index and compare routing results.

## Commands

```bash
python scripts/record-selection-memory.py --query "<request>" --outcome missed --route-type "<level>" --category "<category>"
python scripts/self-grow.py --index-dir ".skill-index"
```

Keep generated memory and reports local. Never include them in a published release.
