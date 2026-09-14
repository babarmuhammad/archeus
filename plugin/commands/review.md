---
description: Review the current diff with archeus's reviewer
---

Run `archeus review $ARGUMENTS` with the Bash tool from the project root.

Useful arguments, passed straight through: `--staged` to review the index
instead of the working tree, `--branch <base>` to review a whole branch against
its base, `--min-confidence <n>` to raise the bar on what is reported.

The reviewer reads this project's learned lessons as conventions, so its
findings are about THIS codebase rather than generic advice. Report what it
found, grouped by file, most serious first — and when it found nothing, say so
in one line rather than inventing something to say. If the command is not
found, say archeus is not installed (`pip install archeus`).
