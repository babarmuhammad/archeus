---
description: Pull this project's task-relevant memory into the conversation
---

Run `archeus recall "$ARGUMENTS"` with the Bash tool from the project root,
and read the result as project context before answering.

`archeus recall` scores archeus's semantic memory graph for this project
against the query and prints only the subgraph that fits a token budget — it is
local, needs no model call, and returns in well under a second. If the command
is not found, tell the user archeus is not installed
(`pip install archeus`) and continue without it.

If it prints `(no relevant project memory)` there is simply nothing recorded
for this topic yet: say so once, briefly, and carry on. Do not re-run it with
different phrasings.

With no arguments, recall against the task the user just described.
