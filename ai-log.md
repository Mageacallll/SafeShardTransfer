# AI Interaction Log (Concise)

This document summarizes how AI (ChatGPT) was used during the development of this project.

The goal is not to document every interaction, but to show how AI contributed to **design decisions, debugging, and reflection**, while the final decisions remained our own.

---

## 1. Early Design Clarification (Mar 11–13)

**Context:**  
We had initial design documents describing a shard reassignment protocol.

**AI Usage:**  
- Clarified concepts such as:
  - epoch semantics
  - ownership fencing
  - per-shard vs per-server state
- Validated the correctness of our state machine structure

**Outcome:**  
We solidified key design commitments:
- epoch-based ownership
- per-shard state machine
- coordinator-driven control

---

## 2. Simulation Architecture Decisions (Mar 13)

**Context:**  
We needed to decide how to implement and test the system.

**AI Usage:**  
- Discussed tradeoffs between:
  - real distributed deployment vs simulation
  - deterministic vs non-deterministic execution

**Outcome:**  
We chose a **deterministic discrete-event simulator** to:
- enable reproducibility
- precisely control failures
- simplify debugging

---

## 3. Protocol Implementation & Debugging (Mar 13–16)

**Context:**  
During implementation of coordinator, server, and message flows.

**AI Usage:**  
- Helped reason about:
  - event ordering issues
  - epoch validation logic
  - invariant enforcement
- Assisted in debugging unexpected behaviors in tests

**Outcome:**  
We refined:
- request rejection conditions
- transfer flow correctness
- invariant test coverage

---

## 4. Failure Injection Design (Mar 16)

**Context:**  
We introduced adversarial scenarios (message drop, crash).

**AI Usage:**  
- Helped enumerate meaningful failure scenarios
- Discussed expected protocol behavior under failures

**Outcome:**  
We implemented:
- fault injection scenarios
- failure classification (stall vs success)
- structured experiment runs

---

## 5. Metrics & Evaluation (Mar 24)

**Context:**  
We added metrics to quantify behavior.

**AI Usage:**  
- Suggested useful measurements:
  - freeze duration
  - reassignment completion time
  - client request failures

**Outcome:**  
We implemented a metrics collector and integrated it into experiments.

---

## 6. Key Insight Development (Mar 24–26)

**Context:**  
Analyzing experiment results.

**AI Usage:**  
- Helped interpret results
- Challenged assumptions about correctness

**Critical realization:**
- Correct reassignment ≠ client-visible correctness
- Safety mechanisms directly impact liveness and availability

---

## 7. README & Reflection Structuring (Mar 26)

**Context:**  
Preparing final submission.

**AI Usage:**  
- Helped restructure README to:
  - highlight tradeoffs
  - surface learning outcomes
  - align with rubric expectations
- Assisted in drafting reflection narrative

**Outcome:**  
We transformed the project from:
- “a working system”

to:

- “a system that demonstrates a concrete safety vs availability tradeoff”

---

## Final Notes

AI was used as a **reasoning assistant**, not as a source of final answers.

In all cases:
- we validated suggestions against our implementation
- we made final design and implementation decisions ourselves

The most valuable contribution of AI was:
> helping us articulate and recognize the tradeoffs revealed by our system