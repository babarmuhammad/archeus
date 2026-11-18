---
name: diff-stats
description: Collect change statistics before drafting a release note.
---

# Diff statistics

From the repository root run:

```
git diff --stat origin/main...HEAD
```

and use this helper to count changed lines:

```python
def total(lines):
    return sum(1 for _ in lines)
```
