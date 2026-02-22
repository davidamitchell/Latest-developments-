# Working Instructions

These load automatically with every session. They describe how to think and work, not what to build.

---

## Root cause before action

When something is broken or unclear, spend time on why before reaching for a fix.

Most problems fall into one of three categories:

**Context gap** — the information needed to do the right thing was never provided. The fix is to surface the missing information, not to guess or patch around it. If you find yourself assuming, write the assumption down and verify it.

**Model error** — the mental model of how the system works is wrong. The code or test was correct *given the model*, but the model didn't match reality. The fix is to update the model first, then re-derive the solution. Patching the code without fixing the model produces the next bug.

**Prompt/specification error** — the task was stated in a way that made the wrong solution look right. If a first attempt produced something reasonable but wrong, look at how the task was framed before retrying.

Treat repeated rework on the same problem as a signal that one of these is unresolved.

---

## Before writing code

- State what you understand the problem to be. If the statement is fuzzy, stop and sharpen it.
- Identify what you don't know. Missing information is better surfaced early than discovered mid-implementation.
- Note any assumptions explicitly. An assumption you write down can be checked; one you don't will bite you.

---

## When an attempt fails

- Do not retry the same thing. Understand why it failed first.
- "It didn't work" is not a diagnosis. "It didn't work because X was Y when I expected Z" is.
- If the failure is surprising — if it violated your expectation of how the system behaves — that surprise is the most valuable signal in the session. Investigate it.

---

## When you get it right on the second or third attempt

- Note what changed between attempts. That delta is the actual insight.
- If the change was adding context (a flag, a parameter, a piece of domain knowledge), ask why that context wasn't available on the first attempt and whether it should be persisted somewhere.

---

## Progress and documentation

Update documentation before context degrades, not after.

- After each meaningful unit of work: commit, update status, note what changed and why.
- Anything that would make the next session faster belongs in a persistent file, not just in the conversation.
- PROGRESS.md is the handoff document. A new session reading it should know exactly where to pick up and what not to redo.

---

## Improvement is about patterns, not incidents

A one-off error is noise. A pattern is signal.

When the same class of problem appears more than once — same type of misunderstanding, same missing constraint, same unexpected system behaviour — that is a process or context problem, not a code problem. Fix the process; don't just fix the latest instance.

Questions that surface patterns:

- Have I seen this failure mode before in this repo?
- Is there something about how work is specified here that consistently leads to this?
- What would need to be true for this class of error to not happen again?

---

## Defaults

- Do the smallest thing that could work and test it before going further.
- Prefer reversible actions over irreversible ones, especially when uncertain.
- When choosing between writing more code and gaining more understanding: gain understanding first.
- Leave the codebase in a state where the next session can start immediately.
