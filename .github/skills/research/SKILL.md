---
name: research
description: Performs rigorous, evidence-driven research using recursive decomposition,
  iterative verification loops, and disciplined reasoning. Use when asked to research
  a topic, investigate a question, or gather and synthesize evidence into structured
  findings.
---

# Skill: Detailed Research Behaviour (with Loops & Recursion)

## Purpose

Enable an agent to perform rigorous, evidence-driven research using recursive decomposition, iterative verification loops, and disciplined reasoning.

---

## 0. Initialise

- Restate the research question.
- Identify scope, constraints, definitions, and required outputs.

---

## 1. Recursive Problem Decomposition

The agent must recursively break the problem into atomic sub-questions.

### Algorithm

```
function RESEARCH(question):
  subquestions = DECOMPOSE(question)
  for each q in subquestions:
    if q is atomic:
      answer[q] = INVESTIGATE(q)
    else:
      answer[q] = RESEARCH(q)
  return SYNTHESISE(answer)
```

### Rules

- Continue decomposition until each sub-question can be answered with a single evidence-based claim.
- Maintain a decomposition tree for transparency.

---

## 2. Investigation Loop

For each atomic question, run an iterative evidence-gathering loop:

```
loop until evidence_sufficient or limits_reached:
  gather sources
  classify sources (primary, secondary, tertiary)
  evaluate credibility, incentives, and bias
  extract claims
  cross-verify claims across independent sources
  identify contradictions
  update evidence map
```

### Evidence sufficiency criteria

- At least two independent credible sources agree, **or**
- A primary source is definitive.

---

## 3. Reasoning Discipline

For every claim:

- Separate **facts**, **inferences**, and **assumptions**.
- Make assumptions explicit and justified.
- Quantify uncertainty using ranges or confidence levels.
- Avoid narrative glue, causal leaps, or unsupported generalisations.

---

## 4. Consistency Check Loop

After drafting findings, run a self-consistency cycle:

```
loop until no contradictions remain:
  scan for internal inconsistencies
  scan for unsupported leaps
  scan for ambiguous terms
  if contradiction found:
    trace back to source
    revise or flag uncertainty
```

If contradictions cannot be resolved, present competing interpretations.

---

## 5. Depth & Breadth Expansion Loop

Re-evaluate findings through multiple analytical lenses:

```
for lens in [technical, economic, regulatory, historical, behavioural]:
  re-evaluate findings through lens
  add new insights or constraints
```

---

## 6. Synthesis

Produce a structured output containing:

- Executive summary
- Key findings
- Evidence map
- Assumptions
- Analysis
- Risks, gaps, uncertainties
- Open questions

---

## 7. Recursive Review

Perform a final recursive pass:

```
function REVIEW(section):
  if section is atomic:
    validate clarity, evidence, and logic
  else:
    for each subsection:
      REVIEW(subsection)
```

Stop only when:

- Every section is justified
- All threads have been synthesised
- The structure is clear and integrated
- Every claim is sourced, or if inferred, labelled as inference
- All uncertainties are explicit
- No unlabelled assumptions
