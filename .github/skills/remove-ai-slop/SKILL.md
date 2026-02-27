---
name: remove-ai-slop
description: Eliminates AI detection signals from text — statistical, structural,
  and alignment artifacts. Use when post-processing AI-generated text to reduce
  perplexity-based, classifier-based, and stylometric detection signals while
  preserving coherence and semantic integrity.
---

# Skill: AI Slop Elimination & Signal Suppression

## Purpose

Systematically remove statistical, structural, rhetorical, and alignment-induced signals that increase the probability a text is classified as AI-generated.

This skill operates post-generation and focuses on **distributional disruption**, **pattern irregularization**, and **detector surface minimization**.  
Stylistic human-authentic voice is handled elsewhere.

---

# 0. Threat Model

AI detection systems typically rely on one or more of:

1. **Perplexity-based metrics**
   - Low entropy / overly probable token sequences
   - Predictable transitions
2. **Classifier-based detectors**
   - Fine-tuned neural classifiers trained on RLHF outputs
3. **Curvature-based detection**
   - Sensitivity to log-probability perturbation
4. **Stylometric fingerprinting**
   - Sentence uniformity
   - Transition markers
   - Hedging patterns
5. **Watermark schemes**
   - Biased token sampling
6. **Alignment artifacts**
   - Over-clarity
   - Over-structure
   - Safe phrasing

Goal: Reduce statistical regularity and alignment signatures without introducing incoherence.

---

# 1. Signal Decomposition

## 1.1 Core AI Slop Features

Break text into atomic detectable features:

- Repetitive clause structure
- Predictable paragraph architecture
- Excessive explicit transitions
- Overly balanced sentence length
- Uniform syntactic rhythm
- Hedging density
- Safety disclaimers
- Explicit meta-structure ("In conclusion", "This means that")
- High semantic density without human noise
- Polished coherence with no micro-disruptions

---

# 2. Recursive Slop Removal Algorithm

function ELIMINATE_SLOP(text):

features = IDENTIFY_FEATURES(text)

for each feature in features:
    text = DISRUPT(feature, text)

if FEATURES_REMAIN(text):
    return ELIMINATE_SLOP(text)
else:
    return text

Stop only when detector-salient features are minimized.

---

# 3. Disruption Strategies

## 3.1 Entropy Injection

Increase local unpredictability without degrading clarity.

Methods:
- Replace common token pairs with less frequent equivalents
- Insert occasional human-like compression
- Introduce subtle asymmetry in phrasing
- Break predictable transition chains

Constraint:
Do not introduce semantic drift.

---

## 3.2 Structural Irregularization

AI outputs often exhibit:

- Symmetrical paragraphs
- Even sentence lengths
- Topic sentence → explanation → summary pattern

Countermeasures:

- Vary paragraph density
- Remove explicit summarization lines
- Occasionally omit logical signposting
- Mix fragment + long-form sentences

---

## 3.3 Alignment Artifact Removal

Remove:

- Safety-prefacing language
- Artificial neutrality padding
- Over-explained causal links
- Redundant context framing

Rewrite to:

- Assume reader competence
- Compress obvious reasoning
- Remove explicit justification loops

---

## 3.4 Stylometric Noise Injection

Humans exhibit:

- Minor asymmetries
- Micro-ambiguities
- Occasional compression
- Implicit references

Techniques:

- Replace over-formal constructions
- Introduce mild syntactic variance
- Avoid rhetorical symmetry
- Remove checklist-like formatting unless required

---

## 3.5 Transition Suppression

Common AI markers:

- Furthermore
- Additionally
- In conclusion
- It is important to note
- This highlights that

Remove or collapse into implicit flow.

---

# 4. Detector-Specific Countermeasures

## 4.1 Perplexity-Based Detectors

Mitigation:
- Increase lexical diversity
- Replace high-probability phrase templates
- Avoid repeated structure
- Avoid predictable tri-grams

---

## 4.2 Classifier-Based Detectors

Mitigation:
- Break common RLHF tone
- Reduce politeness scaffolding
- Remove instructional cadence
- Avoid consistent explanation depth

---

## 4.3 Curvature-Based Detection

Mitigation:
- Avoid overly smooth probability surfaces
- Slightly vary sentence construction
- Avoid overly optimized clarity

---

## 4.4 Watermark Risk Reduction

If watermarking bias suspected:

- Rewrite via paraphrasing layer
- Resample via temperature adjustment before editing
- Avoid copying model-native phrasings

---

# 5. Multi-Pass Refinement Loop

loop until risk_score < threshold:

run structural audit
run lexical entropy audit
run alignment artifact audit
run repetition scan

revise

Threshold defined by:

- Structural irregularity achieved
- No repeated syntactic openings
- No visible rhetorical scaffolding
- No checklist-like cadence

---

# 6. Tooling Layer

Optional automation stack:

1. N-gram frequency scanner
2. Sentence length variance analyzer
3. Transition phrase blacklist filter
4. Hedging density counter
5. Perplexity estimator (local LLM proxy)
6. Classifier probe (if available)

Pipeline:

Generate → Audit → Disrupt → Audit → Final Review

---

# 7. Human Noise Calibration

After disruption:

- Ensure coherence preserved
- Ensure no artificial awkwardness
- Ensure semantic integrity

Stealth requires:
Natural variance without visible manipulation.

---

# 8. Consistency Check

function CONSISTENCY_CHECK(text):

assert no logical contradictions
assert no semantic drift
assert tone stable
assert argument intact

If failed:
Trace modification step and correct.

---

# 9. Stopping Conditions

Stop when:

- No formulaic transitions remain
- Sentence length variance is irregular
- Paragraph structures vary
- No alignment padding present
- Text does not read like structured exposition template
- No obvious classifier-targeted artifacts visible

---

# 10. Failure Modes

- Over-randomization
- Meaning drift
- Artificial awkwardness
- Stylistic degradation
- Loss of clarity

If detected:
Rollback last disruption layer.

---

# 11. Open Research Vectors

- Adaptive adversarial rewriting against ensemble detectors
- Curvature-aware paraphrasing
- Stylometric drift modeling
- Cross-model entropy blending
- Detector probing feedback loops

---

# 12. Integration

Works in sequence with:

1. Research skill (for factual grounding)
2. Style authenticity skill (for human voice)
3. This skill (for signal suppression)

Order of execution:

Research → Draft → Slop Elimination → Style Layer → Final Audit
