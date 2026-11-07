# CashLoop: Project 1, Step 1 golden set

Paths below are relative to the repo root.

25 PO emails with hand-checkable gold labels, for evaluating the PO extractor.

```
corpus/po_emails/po_001.txt ... po_025.txt   the inputs
evals/extraction/gold/po_001.json ...        expected output, resolution, expected issues
evals/extraction/manifest.csv                one row per email: difficulty, tags, issues
evals/extraction/LABELLING_RULES.md          what "correct" means
evals/extraction/reference/                  customers, SKUs and prices the emails use
evals/build_golden_set.py                    regenerates everything (deterministic)
```

**Mix:** 3 easy, 9 medium, 13 hard. 23 POs across 25 emails (3 non-POs, 1 email with two POs), 9 planted issues.

**Reference data** covers only what these emails touch (21 customers, 68 SKUs). In Step 0, make sure your full ERP seed contains these rows unchanged, or the price checks won't line up. Easiest route: load the reference CSVs first, then generate the rest of the seed around them.

**Self-check:** the generator re-derives every expected issue with reference business rules and fails if they don't match the planted ones. Run `python evals/build_golden_set.py` (from the repo root) after any edit.

## Before you use it

1. **Read all 25 emails.** About an hour. Edit anything that feels unrealistic, then update the gold JSON to match.
2. **Add 5 emails you write yourself** as po_026 to po_030, imitating real POs you've seen. If accuracy is much lower on these, the generated set is too easy.
3. **Use a different model for extraction than the one that wrote these emails.** These were written by Claude, so extracting with Claude may score optimistically.
