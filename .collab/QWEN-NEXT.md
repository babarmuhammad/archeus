# Next Qwen launch - prepared 2026-10-15 by Claude

One card is ready for Qwen: **T-071, correction r2** (status `changes`, `owner: qwen`). The card's `notes:` has Codex's five findings verbatim and the full how-to, so Qwen needs nothing else.

## Launch (PowerShell or Git Bash, from D:\\Claude)

Claude now launches Qwen itself, headless (`pi -p ...`), under the owner rule of 2026-10-15: T-071 r2 was started by Claude at ~00:50 on 2026-10-15. The interactive form below is for when you want to watch it.

```
pi --model spark/qwen3.8-flash-next "Read .collab/README.md, then do card T-071 in .collab/BOARD.md: the CORRECTION REQUESTED block in its notes. Edit only .collab/T-071-storage-namespace-options.md and the T-071 card. No web fetch, no code, no tests, no native operation. Sign as Qwen."
```

## When Qwen finishes

1. Check that the T-071 card reads `status: review` and `CORRECTION r2 DONE` in notes, and that `git status --short` shows no tracked file changed (the note and the board are under `.collab/`, excluded from git).
2. Codex re-review, one call:
   ```
   py .collab/analysis_review.py T-071 .collab/T-071-storage-namespace-options.md
   ```
   It writes `.collab/reviews/T-071-analysis.r2.md`.
3. APPROVE: the note is the evidence input for your T-004 (S2-G) mechanism decision. Its options O1-O4 are the choices. CHANGES: same loop.

## Not prepared for Qwen, on purpose

- **T-008** (Windows-only evidence, BLOCKED BY CLASSIFIER) is the other card Qwen could take. It runs real AppContainer profiles, Jobs and processes, so it needs an `auth:` with your words naming those operations before anyone runs it. The README rule: a block label never carries authorization. Claude does not write its prompts, because the classifier stopped Claude on exactly that and said not to produce it again. Route it with `owner: qwen`, `status: ready` and an `auth:` line if you want Qwen to write and run it.
