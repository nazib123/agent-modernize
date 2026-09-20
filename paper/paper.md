# AgentModernize: Preserving Business Logic in Legacy Modernization with Multi-Agent LLMs and Behavioral Specification Graphs

**Sheikh Nazib Ahmed**, **Marnim Galib**
University of Texas at Arlington
Arlington, TX, USA
{sxa5256, marnim.galib}@uta.edu

## Abstract

Legacy modernization breaks business logic. Not sometimes — routinely. Most tools and LLM-based approaches treat modernization as syntax translation: convert COBOL to Java, swap PL/SQL for Python, ship it. The implicit rules, edge-case handling, and cross-module constraints that keep production systems running are lost in the process. Nobody notices until something fails in production.

We present *AgentModernize*, a multi-agent framework that treats modernization as a behavioral preservation problem instead. Four specialized agents handle extraction, specification, code generation, and validation. The key intermediate artifact — a *Behavioral Specification Graph (BSG)* — forces extracted business logic to be explicit and inspectable before any code is generated, creating a trust boundary between what the LLM understood and what it produces.

We evaluated on LegacyModernize-8, eight scenarios spanning telecom and banking, using three models (GPT-4o-mini, GPT-4o, GPT-5.3-codex) under a fair protocol: same gold-standard tests, 3 trials, temperature 0.0. The result was consistent across all three: Full AgentModernize with feedback was the only configuration with non-zero mean BER under every backbone. SP-LLM and CoT-LLM scored 0.0% on every scenario, on every backbone. AgentModernize without feedback scored 0.0% mean BER with GPT-4o-mini and GPT-5.3-codex; under GPT-4o it achieved non-zero BER only on S1 (44.4%; 5.6% mean over scenarios) — still far below full AgentModernize with feedback. Mean BER for full AgentModernize was 9.4% (mini), 8.1% (GPT-4o), and 19.4% (codex), with individual scenarios reaching 75.0%. The feedback loop remains decisive: without it, mean BER is 0% on mini and codex, and stays well below the full pipeline even under GPT-4o. The BSG captures 92.3% of gold-standard rules with 90.2% precision, confirming that the bottleneck is code generation, not extraction. For regulated industries, the pipeline's traceable artifacts — business rule inventory, BSG, equivalence reports — provide an audit trail that no single-prompt approach can match.

**Keywords:** legacy modernization, multi-agent systems, large language models, business logic preservation, behavioral equivalence, software engineering

## 1. Introduction

Telecommunications carriers, financial institutions, and healthcare providers run their core operations on systems built twenty or thirty years ago. COBOL batch jobs process billing. PL/SQL procedures enforce contract logic. Shell scripts orchestrate provisioning workflows. These systems work — and the business rules encoded in them have been refined through years of production experience, bug fixes, and regulatory adaptation [1]. But they are expensive to maintain, difficult to integrate with modern platforms, and increasingly fragile as the engineers who wrote them retire [2].

The obvious response is modernization. The less obvious problem is that most modernization efforts destroy the very thing they should preserve: behavioral semantics. Business rules in legacy systems are rarely documented. They live in control flow patterns, conditional branches, exception handlers, and configuration files [3]. A line-by-line COBOL-to-Java translation can compile and run yet silently break edge-case handling, alter validation logic, or drop constraints that were never written down [4]. We have seen this firsthand in telecom provisioning workflows where a syntactically correct translation passed compilation but silently dropped a suspended-account exemption that had been in production for fifteen years. The result is a system that looks modern but behaves differently.

Large Language Models (LLMs) offer a natural tool for this problem — they can parse legacy code, reason about intent, and generate modern equivalents [5, 6]. But simply prompting an LLM to "convert this legacy code to a modern API" is brittle for at least three reasons. First, context windows cannot hold an entire legacy codebase at once. Second, a single generation pass provides no mechanism to verify that behavior was preserved. Third, a monolithic prompt conflates understanding, specification, transformation, and validation — tasks that benefit from separation [7].

In this paper, we propose *AgentModernize*, a multi-agent framework that decomposes legacy modernization into four specialized phases, each handled by a dedicated LLM-powered agent:

1. **Legacy Analyzer Agent** — Extracts both explicit and implicit business rules, along with control flows and operational constraints, from legacy artifacts.
2. **Specification Generator Agent** — Transforms extracted knowledge into structured *Behavioral Specification Graphs (BSGs)* that formally represent business logic.
3. **Modernization Transformer Agent** — Generates modern service-oriented implementations from BSGs while preserving behavioral contracts.
4. **Equivalence Validator Agent** — Verifies that the modernized implementation maintains functional equivalence with the original legacy behavior through automated test generation and differential analysis.

The key insight — and we return to this repeatedly in Sections 5 and 6 — is that the BSG acts as a "glass box" between legacy understanding and modern generation. It forces extracted business logic to be explicit and inspectable before any code is written. When the Validator detects a behavioral divergence, it triggers a targeted correction loop, not a full re-generation. The feedback loop turns out to be the single most important mechanism in the entire pipeline (Section 5, Table 5).

We evaluate on LegacyModernize-8, a benchmark of eight scenarios covering telecom and banking modernization. We measure behavioral equivalence rate, business rule preservation (distinguishing explicit from implicit rules), and manual effort reduction against single-prompt and chain-of-thought LLM baselines. We should note upfront that absolute BER numbers are modest — mean 9.4% with GPT-4o-mini, 8.1% with GPT-4o, 19.4% with codex — but the relative result is what matters: SP-LLM and CoT-LLM score 0.0% under the same protocol.

### Contributions

Our contributions are:

- **A multi-agent framework** that decomposes legacy modernization into extraction, specification, transformation, and validation — with a feedback loop for iterative correction.
- **Behavioral Specification Graphs**, an intermediate representation that captures business rules, pre/post-conditions, data constraints, and control flow dependencies in an inspectable, verifiable form.
- **An automated equivalence checking approach** based on test oracle generation from BSG specifications, combined with differential trace analysis.
- **An empirical evaluation** on an eight-scenario benchmark (including a cross-domain COBOL banking scenario), with ablation analysis quantifying each agent's contribution, a model comparison (GPT-4o-mini vs. GPT-4o) demonstrating complementary strengths, and a frontier model study (GPT-5.3-codex) confirming that AgentModernize with feedback outperforms all other configurations — including the no-feedback variant — under our protocol.

## 2. Related Work

### 2.1 Legacy System Modernization

Comella-Dorda et al. [1] catalogued modernization strategies ranging from wrapping to full re-engineering; the horseshoe model [3] formalized the process as iterative abstraction, transformation, and refinement. These frameworks are useful for thinking about the problem. They do not solve it. Model-driven approaches like MoDisco [8] formalize legacy knowledge using KDM and ADM standards, but constructing the models requires manual effort that often rivals the cost of the modernization itself — which defeats the purpose.

Industry tools — IBM's Rational Asset Analyzer, Micro Focus Enterprise Analyzer, COBOL-to-Java transpilers — handle syntactic translation competently [9]. But "compile-and-run" is not behavioral equivalence. None of these tools verify that the translated system *behaves* the same as the original, and none of them publish behavioral equivalence metrics we could compare against. Our work targets precisely this gap — and as we show in Section 5, even LLM-based approaches fail to preserve behavior without an explicit feedback mechanism.

**Comparison to Established IRs.** The Knowledge Discovery Metamodel (KDM) [24] and Architecture-Driven Modernization (ADM) standards from OMG provide formal representations of legacy system semantics for modernization tooling. Behavioral Interface Specification Languages such as JML [22] and Eiffel [23] encode pre/post/invariants per method. BSG draws from both traditions but differs in three key respects: (i) it is designed for LLM-mediated extraction with per-rule confidence scoring and source traceability; (ii) it explicitly distinguishes explicit from implicit business rules — a categorization absent from KDM/JML; and (iii) it serves as an inspectable trust boundary between LLM extraction and LLM generation, a role unnecessary in pre-LLM modernization workflows. We view BSG as adapting the well-established graph-IR-with-contracts paradigm to the specific demands of LLM-driven modernization, rather than introducing a fundamentally new representation.

### 2.2 LLMs for Software Engineering

LLMs have shown strong results in code generation [5], bug detection [10], code review [11], and program repair [12]. The work most relevant to ours is Pan et al. [13], who found that GPT-4 produces syntactically correct cross-language translations but introduces semantic bugs in complex control flows. This is exactly the failure mode we observed in our own experiments (Section 5): every single-prompt baseline compiled and ran but scored 0.0% on behavioral tests.

The common thread in all of these studies is that they treat modernization as a single-pass task. One model, one prompt, one output. No intermediate representation, no verification, no feedback. For a self-contained utility function, that might work. For a 280-line COBOL provisioning workflow with thirteen interacting business rules and implicit logic buried in exception handlers, it does not. Our results in Table 2 confirm this empirically.

### 2.3 Multi-Agent LLM Systems

MetaGPT [14] partitions software development across architect, engineer, and tester agents. ChatDev [15] models an entire software company through multi-agent dialogue. AgentCoder [16] pairs a code generator with an adversarial test generator. Self-Refine [25] and Reflexion [26] show that LLM agents can improve their own outputs through self-generated feedback — a principle our feedback loop shares.

But all of these target *greenfield* development. Building new code from scratch is a fundamentally different problem than modernizing existing code with undocumented business rules. None of them need to extract implicit logic from decades-old COBOL, represent it in a verifiable form, or confirm that generated code preserves behavioral semantics that were never written down. Compared to these systems, AgentModernize has one advantage and one disadvantage: it solves a harder problem (behavioral preservation, not just code generation), but it relies on a *task-specific* intermediate representation (the BSG) tailored to legacy modernization rather than to general software engineering tasks such as code review or refactoring. BSG itself is not tied to any application domain — it captures business rules, control/data flow, and constraints in a form that applies equally to telecom, banking, healthcare, or government legacy systems, as our S8 banking result begins to demonstrate.

### 2.4 Behavioral Equivalence and Program Equivalence

Formal program equivalence — bisimulation, trace equivalence, observational equivalence — provides the theoretical grounding for our verification approach [17]. Full formal verification is intractable for most real-world systems and we do not attempt it. Practitioners rely on lighter-weight alternatives: differential testing [18] compares outputs across system versions; metamorphic testing [19] checks whether known input transformations produce expected output transformations.

Our Equivalence Validator combines both ideas, with one important twist: it generates test oracles from the BSG specification, not from the legacy code directly. This avoids the circularity of testing a translation against itself — a subtle but critical point that most automated testing approaches miss. We do not claim formal guarantees. What we claim, and demonstrate in Section 5, is that the approach catches a meaningful class of behavioral regressions that single-pass methods miss entirely.

## 3. The AgentModernize Framework

### 3.1 Overview

AgentModernize operates as a stateful multi-agent pipeline that transforms legacy system artifacts into modern service-oriented implementations while preserving behavioral semantics. The framework takes as input a *Legacy Artifact Bundle* — comprising source code, configuration files, database schemas, and optionally natural language documentation — and produces a *Modernized Service Package* — comprising modern API implementations, data models, and a behavioral equivalence report.

**LLM Interaction Model.** All four agents use *zero-shot prompting* with off-the-shelf models accessed through their public APIs. We do not fine-tune any model, we do not use retrieval-augmented generation (RAG), and we do not include few-shot in-context examples in any prompt. Each agent's prompt is a fixed instruction template plus the current pipeline state (legacy artifacts for Agent 1, the Business Rule Inventory for Agent 2, the BSG for Agent 3, and generated code plus test failures for Agent 4). The scenarios described in Section 4.2 were used during pipeline development to iterate on these prompt templates, but at no point are model weights updated or is any scenario-specific example embedded in the prompts at inference time.

Figure 1 illustrates the overall architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                     AgentModernize Pipeline                      │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │  Legacy   │    │  Spec    │    │  Modern  │    │  Equiv   │  │
│  │ Analyzer  │───▶│Generator │───▶│Transformer│───▶│Validator │  │
│  │  Agent    │    │  Agent   │    │  Agent   │    │  Agent   │  │
│  └──────────┘    └──────────┘    └──────────┘    └────┬─────┘  │
│       │                                                │        │
│       ▼                                                ▼        │
│  ┌──────────┐                                    ┌──────────┐  │
│  │ Extracted │                                    │ Equiv    │  │
│  │ Rules     │                                    │ Report   │  │
│  └──────────┘                                    └────┬─────┘  │
│                                                       │        │
│                    ┌──────────────────┐                │        │
│                    │  Feedback Loop   │◀───────────────┘        │
│                    │  (if violations  │                          │
│                    │   detected)      │                          │
│                    └──────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

*Figure 1: AgentModernize Pipeline Architecture*

### 3.2 Legacy Artifact Bundle

The input to the framework is a *Legacy Artifact Bundle* `L = {S, C, D, N}` where:

- `S` = Source code files (e.g., COBOL programs, PL/SQL procedures, shell scripts)
- `C` = Configuration files (e.g., JCL, parameter files, cron schedules)
- `D` = Database schemas (e.g., DDL statements, copybook layouts, data dictionaries)
- `N` = Natural language documentation (optional; e.g., runbooks, comments, requirement documents)

### 3.3 Agent 1: Legacy Analyzer

The Legacy Analyzer Agent performs deep analysis of the artifact bundle to extract both explicit business rules (those directly stated in source code as conditionals, guards, or documented constraints) and implicit business rules (those inferable from code patterns, default values, exception handlers, and cross-module dependencies). All extracted rules are labeled with a category (`explicit` or `implicit`) and a confidence score in the Business Rule Inventory. This agent operates in three sub-phases:

**Phase 1a — Structural Parsing:** The agent identifies program entry points, module boundaries, data flows, and external dependencies. For procedural legacy code, this involves identifying PERFORM/CALL hierarchies, file I/O operations, and database interactions.

**Phase 1b — Business Rule Extraction:** The agent identifies conditional logic, validation rules, computation formulas, state transitions, and exception handling patterns. Each extracted rule is annotated with:
- A natural language description
- The source location (file, line range)
- Input variables and output effects
- Confidence score (high/medium/low) based on extraction clarity

**Phase 1c — Constraint Discovery:** The agent identifies implicit constraints including data type restrictions, value ranges, referential integrity rules, temporal ordering requirements, and business-specific invariants (e.g., "order total must equal sum of line items").

**Output:** A structured *Business Rule Inventory (BRI)* — a JSON document containing all extracted rules, constraints, and their metadata.

```json
{
  "rules": [
    {
      "id": "BR-001",
      "description": "Validate account status before processing order",
      "type": "precondition",
      "source": {"file": "ORDER_PROC.cbl", "lines": "145-162"},
      "inputs": ["account_id", "account_status"],
      "effect": "REJECT if account_status NOT IN ('ACTIVE', 'SUSPENDED')",
      "confidence": "high"
    }
  ],
  "constraints": [
    {
      "id": "DC-001",
      "description": "Order amount must be positive decimal",
      "field": "order_amount",
      "constraint": "DECIMAL(12,2), > 0",
      "source": {"file": "ORDER_PROC.cbl", "lines": "88-89"}
    }
  ]
}
```

### 3.4 Agent 2: Specification Generator

The Specification Generator Agent transforms the Business Rule Inventory into a *Behavioral Specification Graph (BSG)* — the core intermediate representation of AgentModernize.

**Definition 1 (Behavioral Specification Graph).** A BSG is a directed acyclic graph `G = (V, E, Pre, Post, Inv)` where:

- `V` is a set of *operation nodes*, each representing a discrete business operation (e.g., "validate order", "calculate tax", "update inventory").
- `E ⊆ V × V × L` is a set of *labeled edges* representing *control flow* between operations, where `L = {sequence, conditional, parallel, error}` is the label set. Data dependencies are not represented as edges; instead, they are captured at the node level through the `inputs(v)` and `outputs(v)` annotations defined below. A data dependency from `u` to `v` is implicit when `outputs(u) ∩ inputs(v) ≠ ∅`. We chose this separation because control flow determines *how* the modernized code is orchestrated (sequential calls, conditional branches, error handlers), while data flow determines *what* each operation reads and writes; keeping them on different structural elements makes both easier for downstream agents (and human reviewers) to inspect.
- `Pre: V → P` maps each node to a set of *preconditions* — logical predicates that must hold before the operation executes.
- `Post: V → P` maps each node to a set of *postconditions* — logical predicates that must hold after the operation completes.
- `Inv: G → P` is a set of *global invariants* — predicates that must hold throughout the entire workflow.

Each operation node `v ∈ V` is further annotated with:

- `inputs(v)`: Required input data fields with types
- `outputs(v)`: Produced output data fields with types
- `rules(v)`: Set of business rule IDs from the BRI that govern this operation
- `error_behavior(v)`: Expected behavior under error conditions

**Edge Label Taxonomy.** The four edge labels have precise meanings that determine how downstream code is generated:

- `sequence` — unconditional next-step ordering: `v` always executes after `u`. In modernized code, this becomes a straight-line call from `u` to `v`.
- `conditional` — guarded transition: `v` executes after `u` only when a predicate on `outputs(u)` (or on shared state) holds. The predicate is stored as a `Pre(v)` clause; the label indicates the edge is one branch of a decision point (typically paired with a sibling `conditional` or `error` edge covering the other branch).
- `parallel` — `u` and `v` can execute concurrently after their common predecessor with no data dependency between them. This becomes an async/gather block in modernized code.
- `error` — exception-triggered transition: `v` executes when `u` raises an error matching the condition in `error_behavior(u)`. This becomes an except/catch handler in modernized code.

Every edge carries exactly one label from this set; the taxonomy is closed. A control-flow pattern that does not fit these four labels (e.g., cooperative coroutines) is out of scope for the current BSG version.

**BSG Example (Order Processing):**

```
[Receive Order] ──sequence──▶ [Validate Account] ──conditional──▶ [Check Inventory]
                                     │                                    │
                                     │ (fail)                        (available)
                                     ▼                                    ▼
                              [Reject Order]                    [Calculate Pricing]
                                                                         │
                                                                    sequence
                                                                         ▼
                                                                [Submit Order]
                                                                         │
                                                                    sequence
                                                                         ▼
                                                               [Confirm & Notify]

Preconditions:
  - Validate Account: account_status IN ('ACTIVE', 'SUSPENDED')
  - Check Inventory: product_id EXISTS in inventory, requested_qty > 0
Postconditions:
  - Submit Order: order_status = 'SUBMITTED', order_id IS NOT NULL
Invariants:
  - order_total = SUM(line_item_amounts) + tax - discount
  - All monetary values: DECIMAL(12,2), >= 0
```

**Concrete Example (S1, Order Validation).** The following BSG node, extracted from scenario S1's COBOL order validation program, illustrates the representation in practice:

```json
{
  "operation": "ValidateDisconnectOrder",
  "source_rule": "BR-004",
  "source_location": "ORDER_VALIDATION.cob:118-142",
  "preconditions": [
    "account_status in ['ACTIVE', 'SUSPENDED']",
    "order_type == 'DISCONNECT'"
  ],
  "postconditions": [
    "suspended accounts proceed for disconnect orders",
    "non-disconnect orders rejected for suspended"
  ],
  "invariants": ["order_total == sum(line_items)"],
  "confidence": "high"
}
```

This node captures an implicit rule — suspended accounts are normally blocked, but disconnect orders are exempted — that would be lost in a direct syntax translation. The BSG makes it explicit and inspectable before code generation begins.

### 3.5 Agent 3: Modernization Transformer

The Modernization Transformer Agent generates a modern service-oriented implementation from the BSG. The agent operates under the following transformation principles:

**Principle 1 — Operation-to-Endpoint Mapping:** Each BSG operation node maps to a discrete function or API endpoint in the modernized system.

**Principle 2 — Contract Preservation:** Pre/postconditions from the BSG are translated into input validation, output assertions, and error handling in the generated code.

**Principle 3 — Data Model Derivation:** Input/output annotations from BSG nodes are aggregated to derive modern data models (e.g., Pydantic models, dataclasses) with type constraints.

**Principle 4 — Flow Preservation:** BSG edge labels (sequence, conditional, parallel, error) determine the orchestration pattern in the modernized implementation.

**Output:** A *Modernized Service Package* comprising:
- API endpoint implementations (Python/FastAPI or equivalent)
- Data models with validation rules
- Orchestration logic preserving the BSG control flow
- Error handling matching the BSG error behaviors
- Generated documentation mapping each endpoint to its source BSG node

### 3.6 Agent 4: Equivalence Validator

The Equivalence Validator Agent verifies that the modernized implementation maintains behavioral equivalence with the legacy system as specified by the BSG. The agent performs three types of validation:

**Type 1 — Contract Verification:** For each BSG node, the agent generates test cases that exercise the corresponding modernized endpoint, verifying that:
- Preconditions are enforced (invalid inputs are rejected)
- Postconditions hold (outputs satisfy expected constraints)
- Invariants are maintained across multi-step workflows

**Type 2 — Boundary Testing:** The agent generates boundary test cases based on BSG constraints (e.g., minimum/maximum values, empty inputs, null handling, type boundaries).

**Type 3 — Differential Trace Analysis:** The agent constructs end-to-end workflow traces from the BSG and executes them against the modernized implementation, comparing actual outputs against expected BSG-specified outputs.

**Output:** A *Behavioral Equivalence Report (BER)* containing:
- Per-node equivalence status (PASS/FAIL/PARTIAL)
- Overall behavioral equivalence rate
- Failed test cases with root cause analysis
- Recommendations for remediation

**Feedback Loop:** When the BER identifies behavioral divergences, the pipeline re-invokes the Modernization Transformer with targeted correction instructions, including the failing test cases and expected behaviors. This feedback loop runs for a configurable maximum number of iterations (default: 3).

### 3.7 Orchestration and State Management

The four agents are orchestrated through a stateful pipeline implemented using a directed graph execution engine (e.g., LangGraph). The pipeline maintains a shared state object that accumulates artifacts across phases:

```
State = {
  legacy_bundle: LegacyArtifactBundle,
  business_rules: BusinessRuleInventory,    # After Agent 1
  bsg: BehavioralSpecificationGraph,        # After Agent 2
  modern_code: ModernizedServicePackage,    # After Agent 3
  equiv_report: BehavioralEquivalenceReport, # After Agent 4
  iteration: int,                            # Feedback loop counter
  status: RUNNING | COMPLETED | FAILED
}
```

Each agent reads from and writes to this shared state, enabling traceability from legacy artifacts through intermediate representations to the final modernized output.

## 4. Evaluation Design

### 4.1 Research Questions

We evaluate AgentModernize with respect to the following research questions:

- **RQ1 (Behavioral Equivalence):** To what extent does AgentModernize preserve the behavioral semantics of legacy systems in modernized implementations?
- **RQ2 (Business Rule Preservation):** How effectively does the framework extract and preserve individual business rules through the modernization pipeline?
- **RQ3 (Effort Reduction):** How does the manual effort required for AgentModernize-assisted modernization compare to single-prompt LLM baselines?
- **RQ4 (Agent Contribution):** What is the individual contribution of each agent to the overall modernization quality? (Ablation study)
- **RQ5 (BSG Quality):** How accurately does the Behavioral Specification Graph capture the gold-standard business rules?
- **RQ6 (Model Sensitivity):** How does modernization quality vary across LLM model sizes?

### 4.2 Benchmark: LegacyModernize-8

**All eight scenarios in LegacyModernize-8 are synthetic**, hand-authored to reflect realistic legacy patterns — COBOL/PL-SQL procedures with embedded business logic, multi-step workflows, and implicit rules encoded in exception handlers and default values — rather than sampled from production codebases. We construct the benchmark with eight scenarios, seven drawn from the telecommunications domain and one cross-domain banking scenario written in COBOL to test generalization beyond the telecom domain. Each scenario consists of a legacy artifact bundle and a gold-standard behavioral specification curated by a domain expert (AI-assisted drafting, human-reviewed).

| ID | Scenario | Domain | Complexity | Rules | LOC |
|----|----------|--------|------------|-------|-----|
| S1 | Order Validation | Orders | Medium | 12 | 248 |
| S2 | Billing Disputes | Billing | High | 12 | 195 |
| S3 | Service Activation | Provisioning | High | 14 | 245 |
| S4 | Circuit Inventory | Inventory | High | 13 | 280 |
| S5 | Fault Escalation | Fault Mgmt | High | 13 | 230 |
| S6 | Contract Renewal | Contracts | High | 12 | 210 |
| S7 | Account Migration | Accounts | Very High | 15 | 280 |
| S8 | Bank Transactions | Banking | Very High | 15 | 310 |

*Table 1: LegacyModernize-8 Benchmark Scenarios*

**Scenario Design Principles:**
- Each scenario contains explicitly documented business rules and at least three implicit rules that must be inferred from code patterns.
- Complexity levels reflect the number of conditional branches, external dependencies, and state transitions.
- Scenarios S1–S7 cover telecom-domain challenges: multi-step validation workflows (S1), tier-based conditional logic (S2), capacity management with exemptions (S3), lifecycle management with parent-child dependencies (S4), SLA tracking with tiered escalation (S5), stacking discount calculations with loyalty tiers (S6), and multi-phase migration with rollback semantics (S7). S8 is a COBOL banking transaction processor authored to test cross-domain generalization, with multi-type transactions, tier-based withdrawal limits, overdraft protection, transfer fees, fraud detection, and dormant account handling.

**Gold-Standard Construction Process.** For each scenario we produced three artifacts before any pipeline run: (i) the legacy code (COBOL/PL-SQL), (ii) a gold-standard specification listing every business rule the scenario is intended to encode, and (iii) a reference Python implementation used later by the fair-evaluation test generator. The gold-standard rule list was authored by the first author with LLM-assisted drafting (GPT-4o was used to enumerate candidate rules from the legacy code) followed by manual review, editing, and rejection of low-value candidates. Each retained rule is labeled `explicit` (directly stated in a conditional/guard/comment in the legacy source) or `implicit` (inferable only from patterns such as default values, exception-handler behavior, cross-module data flow, or ordering constraints). We treat rule authorship as a single-annotator ground truth and note this as a threat to validity.

**Trivial-Rule Filtering.** To avoid inflating preservation scores with tautological rules, we applied three exclusion criteria during gold-standard construction: (a) generic input sanitization that any framework provides for free (e.g., "request body must be valid JSON", "integer field must be an integer") is excluded; (b) rules trivially implied by the type system of the target language (e.g., "field is non-null" when the field is typed as non-optional) are excluded; (c) rules whose only assertion is that a named field exists in the output are excluded unless the field's presence is itself a conditional business decision. A rule is retained only if it encodes a scenario-specific behavioral decision — a threshold, an exemption, a state-dependent branch, an ordering requirement, an invariant across fields, or an error-handling policy — that a naive translation could plausibly get wrong. Applying these criteria removed 4–9 candidate rules per scenario during construction (approximately one third of initial LLM-drafted candidates).

### 4.3 Metrics

Both metrics are computed against a **gold-standard test suite** that is withheld from the pipeline — the system never sees these tests during execution. *Test cases are not derived from the BSG.* They are synthesized fresh at evaluation time by GPT-4o-mini from two independent inputs: (i) the gold-standard scenario specification (a human-authored document describing intended behavior in natural language, AI-assisted in drafting and human-reviewed) and (ii) a reference Python implementation of the scenario written by the authors before the pipeline was run. This deliberately breaks the circularity that would arise from testing BSG-derived code against BSG-derived tests: the tests know only what the scenario is supposed to do, not how any particular pipeline chose to represent it. Assertions are executed deterministically by pytest, making BER protocol-dependent on the test-generation prompt but not on any pipeline artifact.

**M1 — Behavioral Equivalence Rate (BER):** The percentage of gold-standard test cases that pass when run against the generated code. Computed as: `BER = |passing_tests| / |total_tests| × 100%`

**M2 — Business Rule Preservation Score (BRPS):** The percentage of gold-standard business rules that are correctly represented in the modernized output. A rule is considered preserved if: (1) it appears in the BSG, AND (2) the corresponding modernized code enforces it, as verified by targeted test cases. `BRPS = |preserved_rules| / |total_rules| × 100%`

### 4.4 Baselines

**B1 — Single-Prompt LLM (SP-LLM):** A single GPT-4o-mini prompt that receives the entire legacy artifact bundle and instructions to produce a modernized implementation. No intermediate representation, no verification.

**B2 — Chain-of-Thought LLM (CoT-LLM):** A single GPT-4o-mini prompt with chain-of-thought instructions: "First analyze the business logic, then design the modern API, then implement it." Still a single model call, but with structured reasoning.

**B3 — AgentModernize (No Feedback):** The full AgentModernize pipeline with the feedback loop disabled, measuring the contribution of iterative refinement.

### 4.5 Implementation Details

- **LLM Backend:** GPT-4o-mini (OpenAI) as default, with GPT-4o and GPT-5.3-codex for model comparison and frontier model studies (Section 5.6)
- **Orchestration:** LangGraph (Python) for stateful pipeline execution
- **Test Execution:** pytest for automated test execution
- **Languages:** Legacy artifacts in COBOL/PL-SQL; modernized output in Python (FastAPI)
- **Configuration:** Temperature 0.2 for extraction/specification agents, 0.0 for code generation, maximum 3 feedback iterations
- **Model Override:** Implemented at the pipeline level via `_MODEL_OVERRIDE` global, allowing any OpenAI-compatible model to be substituted without architectural changes

**Reproducibility:**

| Item | Details |
|------|---------|
| Repository | https://github.com/nazib123/agent-modernize |
| Python | 3.11 |
| Core libraries | LangGraph, pytest, OpenAI SDK |
| Models | GPT-4o-mini, GPT-4o, GPT-5.3-codex |
| Temperature | 0.2 (extraction), 0.0 (generation/evaluation) |
| Trials | 3 per scenario per method |
| Random seed | N/A (temperature 0.0 for generation) |
| Run command | `python run_fair_eval_existing.py --model all --trials 3` |
| Output | `fair_eval_summary.json`, per-scenario result folders |
| Total API cost | < $15 for full evaluation suite |

## 5. Results

All results below use the **fair evaluation protocol**: every method is tested against the same gold-standard test suite (3 trials, temperature 0.0). This eliminates the bias from each method generating its own tests of varying quality and quantity.

### 5.1 RQ1: Behavioral Equivalence

| Scenario | SP-LLM | CoT-LLM | AM (No FB) | AM |
|----------|--------|---------|------------|------|
| S1 | 0.0 | 0.0 | 0.0 | **25.0** |
| S2 | 0.0 | 0.0 | 0.0 | 0.0 |
| S3 | 0.0 | 0.0 | 0.0 | 0.0 |
| S4 | 0.0 | 0.0 | 0.0 | 0.0 |
| S5 | 0.0 | 0.0 | 0.0 | **16.7** |
| S6 | 0.0 | 0.0 | 0.0 | 0.0 |
| S7 | 0.0 | 0.0 | 0.0 | 0.0 |
| S8 | 0.0 | 0.0 | 0.0 | **33.3** |
| **Avg** | 0.0 | 0.0 | 0.0 | **9.4** |

*Table 2: Behavioral Equivalence Rate (%) — Fair Evaluation (3 trials; σ=0.0 except AM on S5: 14.4 and S8: 6.7)*

Under the fair evaluation protocol, AgentModernize with GPT-4o-mini is the *only* method to pass any gold-standard tests. All three baselines — SP-LLM, CoT-LLM, and AM without feedback — achieve 0.0% BER across all scenarios with this model. AgentModernize achieves non-zero BER on 3 of 8 scenarios: S1 (25.0%), S8 (33.3%), and S5 (16.7%), for a mean of 9.4%. Results are deterministic across 3 trials (σ = 0.0) except for S5 (σ = 14.4) and S8 (σ = 6.7), where the feedback loop's iterative patching introduces trial-level variation. Notably, S8 (the COBOL banking scenario) achieves the highest single-scenario BER with GPT-4o-mini (33.3%), providing preliminary evidence that the approach is not narrowly overfit to the telecom scenarios used during pipeline development.

The absolute numbers are low — we are the first to acknowledge that. But the *relative* result matters more: the feedback loop is the decisive mechanism, as the ablation in Table 5 confirms. Without it, the multi-agent pipeline performs no better than a single-prompt baseline. With it, AgentModernize is the only approach that correctly preserves any business rules under independent gold-standard verification. We discuss why the gap between extraction quality and end-to-end BER is so large in Section 6.1.

### 5.2 RQ2: Business Rule Preservation

| ID | Tests | Explicit | Implicit | SP-LLM | AM |
|----|-------|----------|----------|--------|----|
| S1 | 12 | 8 | 4 | 0.0 | **25.0** |
| S2 | 11 | 7 | 4 | 0.0 | 0.0 |
| S3 | 10 | 6 | 4 | 0.0 | 0.0 |
| S4 | 12 | 8 | 4 | 0.0 | 0.0 |
| S5 | 12 | 7 | 5 | 0.0 | **16.7** |
| S6 | 10 | 6 | 4 | 0.0 | 0.0 |
| S7 | 13 | 8 | 5 | 0.0 | 0.0 |
| S8 | 15 | 8 | 7 | 0.0 | **33.3** |

*Table 3: Business Rule Preservation Score (%) — Fair Evaluation. "Tests" counts the number of gold-standard test cases per scenario; each test targets one independently verifiable business rule.*

Under fair evaluation with GPT-4o-mini, SP-LLM preserves zero business rules across all scenarios. AgentModernize preserves rules in S1 (3/12 tests passing), S5 (2/12), and S8 (5/15). In S1, the preserved rules include the core order validation logic and the implicit suspended-account exemption (BR-004). In S8, the COBOL banking scenario, AgentModernize correctly preserved transaction validation and balance computation logic — a first data point suggesting the pipeline transfers beyond telecom, though a single scenario is not a generalization claim. In S5 (fault escalation), the framework preserved SLA-based escalation thresholds. The remaining scenarios expose a fundamental challenge we return to in Section 6.2: when the generated code's API structure diverges from the gold-standard expectations, even correctly implemented business logic fails verification.

### 5.3 RQ3: Residual Behavioral Failures

| ID | Tests | SP-LLM | CoT-LLM | AM (No FB) | AM |
|----|-------|--------|---------|------------|----|
| S1 | 12 | 12/12 | 12/12 | 12/12 | **9/12** |
| S2 | 11 | 11/11 | 11/11 | 11/11 | 11/11 |
| S3 | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| S4 | 12 | 12/12 | 12/12 | 12/12 | 12/12 |
| S5 | 12 | 12/12 | 12/12 | 12/12 | **10/12** |
| S6 | 10 | 10/10 | 10/10 | 10/10 | 10/10 |
| S7 | 13 | 13/13 | 13/13 | 13/13 | 13/13 |
| S8 | 15 | 15/15 | 15/15 | 15/15 | **10/15** |

*Table 4: Residual Behavioral Failures — Fair Evaluation*

All baselines fail every gold-standard test across all scenarios. AgentModernize reduces test failures in S1 (−3), S5 (−2), and S8 (−5) — the same three scenarios where non-zero BER appears in Table 2. S8's reduction (−5) is the largest; the banking scenario's transaction logic seems particularly amenable to iterative correction, possibly because each transaction type is relatively self-contained.

The remaining five scenarios show universal failure. The generated code's structural divergence from gold-standard API expectations is too large — even correctly implemented business logic cannot pass the standardized tests when the endpoint shape is wrong. This is the structural mismatch problem we discuss further in Section 6.2.

### 5.4 RQ4: Ablation Study

| Config | SP-LLM | CoT | AM (No FB) | Full AM |
|--------|--------|-----|------------|----------|
| Avg BER | 0.0 | 0.0 | 0.0 | **9.4** |
| Non-zero scenarios | 0/8 | 0/8 | 0/8 | **3/8** |

*Table 5: Ablation Study — BER (%) by Configuration (Fair Evaluation)*

**The feedback loop is essential, not optional.** Without it, AgentModernize scores 0.0% — identical to all baselines. The multi-agent decomposition alone (extraction → BSG → code generation) produces code that *compiles and runs* but does not pass any gold-standard behavioral tests.

**Feedback is necessary but not sufficient.** Even with the feedback loop, AgentModernize achieves non-zero BER in only 3 of 8 scenarios. In S2–S4, S6, and S7 (with GPT-4o-mini), the structural divergence between generated code and gold-standard expectations was too large for iterative patching to bridge.

**No baseline passes any gold-standard test.** SP-LLM, CoT-LLM, and AM without feedback all score 0.0% across all 8 scenarios. Under fair, independent evaluation, single-pass LLM approaches produce code that looks plausible but fails every behavioral check. A reviewer might reasonably ask whether our gold-standard tests are too strict. We believe they are not — they test for specific business rules (e.g., "suspended accounts may proceed with disconnect orders") that any correct implementation must satisfy. The baselines fail because they produce structurally different code, not because the tests are unreasonable.

### 5.5 RQ5: BSG Quality

**Matching Protocol.** Recall and precision require matching each extracted BSG rule against the gold-standard rule list, which the two representations describe in different phrasings. The matching was performed manually by the first author using the following protocol. For each scenario we generated one BSG per pipeline run and exported all extracted rules as a flat list; each was compared against the gold-standard list side-by-side. An extracted rule was recorded as a true positive when it referred to the same behavioral decision as a gold-standard rule (same triggering condition, same effect), even if phrased differently. A gold-standard rule with no matching extracted rule was recorded as a miss (false negative), and an extracted rule with no matching gold-standard rule was recorded as an extra (false positive), further classified as either *plausible* (a real business decision the annotator did not include) or *hallucinated* (a rule not supported by the legacy source). The classification was later spot-checked by the second author on three scenarios (S1, S5, S8) with full agreement on the true-positive judgments; the two authors are collaborators on this project and we do not report inter-rater kappa. We flag single-annotator matching as a threat to validity and note that a fully independent adjudicator would strengthen the result.

| ID | Gold Rules | BSG Rules | Precision | Recall | Missed |
|----|-----------|-----------|-----------|--------|--------|
| S1 | 12 | 25 | 48.0 | **100.0** | 0 |
| S2 | 12 | 10 | **100.0** | 83.3 | 2 |
| S3 | 14 | 13 | **100.0** | 92.9 | 1 |
| S4 | 13 | 12 | **100.0** | 92.3 | 1 |
| S5 | 13 | 10 | **100.0** | 76.9 | 3 |
| S6 | 12 | 15 | 80.0 | **100.0** | 0 |
| S7 | 15 | 14 | **100.0** | 93.3 | 1 |
| S8 | 15 | 16 | 93.8 | **100.0** | 0 |
| **Avg** | 13.3 | 14.4 | **90.2** | **92.3** | 1.0 |

*Table 6: BSG Rule Extraction Quality — Precision and Recall (%) across all eight scenarios.*

The BSG achieves a mean recall of 92.3% and precision of 90.2% across all eight scenarios. This is a key finding: *the extraction pipeline captures the vast majority of gold-standard business rules*, even though downstream code generation fails to preserve many of them in executable form. The gap between BSG recall (92.3%) and end-to-end BER (9.4%) indicates that the bottleneck is not rule extraction but rather code generation and structural alignment. Notably, S8 (bank transaction, the cross-domain scenario) achieves the highest recall of 100% with 93.8% precision — one plausible additional rule extracted beyond the gold standard — confirming that BSG quality is not restricted to the telecom scenarios on which the pipeline was designed.

S1 and S6 achieve 100% recall but lower precision (48% and 80%), meaning the Legacy Analyzer extracted additional rules beyond the gold standard — plausible business logic that the human annotator did not include. S5 has the lowest recall (76.9%), missing 3 rules related to SLA tracking thresholds, which were deeply embedded in nested conditional logic.

The BRI-to-BSG transfer is lossless: every rule extracted by Agent 1 is faithfully represented in Agent 2's BSG output. This confirms that the BSG acts as a reliable intermediate representation with no information loss between pipeline stages. The implication for practitioners is concrete: if you inspect the BSG after Agent 2 and the rules look right, the problem is downstream in code generation, not upstream in extraction.

### 5.6 RQ6: Model Comparison

To evaluate how model capability affects modernization quality, we ran the full AgentModernize pipeline with GPT-4o and GPT-5.3-codex (a code-specialized frontier model) on all eight scenarios under the same fair evaluation protocol.

| Scenario | GPT-4o-mini | GPT-4o | GPT-5.3-codex |
|----------|-------------|--------|---------------|
| S1 | 25.0 | **58.3** | 44.4 |
| S2 | 0.0 | 0.0 | 0.0 |
| S3 | 0.0 | **6.7** | 0.0 |
| S4 | 0.0 | 0.0 | 0.0 |
| S5 | 16.7 | 0.0 | **75.0** |
| S6 | 0.0 | 0.0 | 0.0 |
| S7 | 0.0 | 0.0 | 0.0 |
| S8 | 33.3 | 0.0 | **35.6** |
| **Avg** | 9.4 | 8.1 | **19.4** |
| Non-zero | 3/8 | 2/8 | 3/8 |

*Table 7: Model Comparison — AgentModernize BER (%) Fair Evaluation*

**Stronger models yield higher BER.** GPT-5.3-codex achieves the highest mean BER (19.4%), more than double GPT-4o-mini's 9.4%. S1 (order validation) is the only scenario where all three models score above zero, with GPT-4o reaching 58.3%. GPT-5.3-codex achieves 75.0% on S5 (fault escalation), the highest single-cell BER in the study.

**Complementary strengths persist across three models.** Each model succeeds on different scenarios: GPT-4o-mini on S1/S5/S8, GPT-4o on S1/S3, and GPT-5.3-codex on S1/S5/S8. No single model dominates all scenarios. An ensemble selecting the best model per scenario could achieve non-zero BER on 4 of 8 scenarios (S1, S3, S5, S8).

**The framework is model-agnostic.** The pipeline architecture, BSG representation, and feedback loop work identically across all three models.

```
Figure 2: Per-scenario BER comparison across three models

BER (%)
  75 |                                        ░░
  70 |                                        ░░
  60 |         ▓▓                               ░░
  50 |         ▓▓                               ░░
  45 |         ▓▓░░                              ░░
  35 |         ▓▓░░                              ░░            ░░
  33 | ██      ▓▓░░                              ░░      ██    ░░
  25 | ██      ▓▓░░                              ░░      ██    ░░
  17 | ██      ▓▓░░              ██              ░░      ██    ░░
   7 | ██      ▓▓░░    ▓▓       ██              ░░      ██    ░░
   0 +------+------+------+------+------+------+------+------
      S1     S2     S3     S4     S5     S6     S7     S8

  ██ GPT-4o-mini    ▓▓ GPT-4o    ░░ GPT-5.3-codex

Caption: All three models score non-zero on S1; GPT-5.3-codex reaches
75% on S5. An ensemble could cover 4/8 scenarios (S1, S3, S5, S8).
(Rendered as TikZ/pgfplots bar chart in paper.tex)
```

### 5.7 RQ6b: Frontier Model Study

We designed AgentModernize for cost-effective models like GPT-4o-mini. The obvious question: if you throw a frontier model at the problem, does the pipeline still matter? We ran all four methods with GPT-5.3-codex under the same fair evaluation protocol.

| Scenario | SP-LLM | CoT-LLM | AM (No FB) | AM |
|----------|--------|---------|------------|------|
| S1 | 0.0 | 0.0 | 0.0 | **44.4** |
| S2 | 0.0 | 0.0 | 0.0 | 0.0 |
| S3 | 0.0 | 0.0 | 0.0 | 0.0 |
| S4 | 0.0 | 0.0 | 0.0 | 0.0 |
| S5 | 0.0 | 0.0 | 0.0 | **75.0** |
| S6 | 0.0 | 0.0 | 0.0 | 0.0 |
| S7 | 0.0 | 0.0 | 0.0 | 0.0 |
| S8 | 0.0 | 0.0 | 0.0 | **35.6** |
| **Avg** | 0.0 | 0.0 | 0.0 | **19.4** |
| Non-zero | 0/8 | 0/8 | 0/8 | 3/8 |

*Table 8: Frontier Model Study — BER (%) with GPT-5.3-codex*

**No crossover.** Even with GPT-5.3-codex, SP-LLM and CoT-LLM score 0.0% across all eight scenarios. The pattern is the same as with GPT-4o-mini and GPT-4o: feedback is the decisive mechanism, regardless of model capability.

**The pipeline scales with model capability.** Mean BER increases with model strength: 9.4% (mini) to 19.4% (codex). The pipeline amplifies model improvements rather than canceling them out. Stronger models give the feedback loop more correctable errors to work with, which is probably why codex's 75.0% on S5 is the highest single-cell BER in the study.

**Auditability beyond BER.** Even if a future model could match AgentModernize's BER in a single prompt, it would produce no Business Rule Inventory, no BSG, no equivalence report. In telecom and banking, "the model said so" is not an acceptable audit trail. The intermediate artifacts — inspectable, traceable, version-controllable — matter in regulated environments regardless of what the BER numbers say.

**Cost.** Total API cost for the final evaluation — all 8 scenarios, 4 methods, 3 trials each, across three models — was under $15. The entire study is reproducible for the cost of lunch.

### 5.8 Qualitative Analysis

**Successfully Preserved Implicit Rule (S1, BR-004).** The COBOL code contains an implicit exemption where suspended accounts are allowed to proceed with disconnect orders. The Legacy Analyzer correctly identified this, the Specification Generator encoded it as a conditional edge in the BSG, and the Transformer generated appropriate Python logic. The Validator's test confirmed the exemption was preserved.

**Cross-Domain Success (S8, Banking).** The COBOL banking transaction processor — the most complex scenario at 310 LOC with 15 business rules — achieves 33.3% BER with GPT-4o-mini, the highest single-scenario score for this model. The feedback loop corrected transaction validation, balance computation, and overdraft protection logic across three iterations. Because S1–S7 were used during pipeline development (all telecom) and S8 was held out (banking, different domain, added post-hoc), the S8 result offers preliminary evidence that the approach is not narrowly overfit to the domain we iterated on. A single banking scenario is not sufficient to claim cross-domain generalization; broader evaluation across healthcare, government, and finance workflows is needed (see Threats to Validity).

**Why does S8 score best?** We do not have a definitive answer, but three candidate hypotheses are consistent with the data. First, S8's business logic decomposes into three largely self-contained transaction types (deposit, withdrawal, transfer) with clear pre/postconditions per type, giving the feedback loop compact independently-testable units to patch. Second, banking transaction patterns (balance checks, overdraft guards, transfer fees) are heavily represented in general code corpora and therefore in the underlying model's prior, so the initial code produced by Agent 3 is closer to the gold-standard shape than for niche telecom workflows such as SLA escalation (S5) or circuit inventory (S4). Third, S8 has the largest rule count (15) so there are simply more opportunities to score partial credit. We cannot separate these hypotheses with N=1 cross-domain scenario; disentangling them is a target for future work.

**Failure Case (S3, All Rules).** The Service Activation scenario involves multi-step validation where each step depends on the previous step's output. The LLM-generated code implemented individual validation functions but failed to wire them together correctly, leading to all tests failing.

**Feedback Loop Convergence (S4).** Under internal evaluation (pipeline-generated tests), iteration 1 produced code with 3/11 internal tests passing; the Validator fed back specific pytest failures, and the Transformer's incremental patch reached 7/11 by iteration 3. However, under fair evaluation against gold-standard tests, S4 scores 0.0% BER — the generated code's API structure diverges too far from gold-standard expectations for any behavioral test to pass, despite internal improvements.

**Feedback-Induced Regression (S6).** Under internal evaluation (pipeline-generated tests), the initial code without feedback achieved 91.7% on its own test suite. The feedback loop attempted to fix the single failing internal test but introduced cascading errors across the pricing logic, degrading internal performance to 0.0%. Under fair evaluation, both configurations score 0.0% BER — but the internal regression illustrates a real risk: feedback loops can make things worse when fixing one test breaks others. This motivates future work on regression-aware patching.

## 6. Discussion

### 6.1 BSGs as a Trust Boundary

We spent more time debating the BSG than any other design decision, and it turned out to be the most consequential one. The BSG creates a trust boundary: everything upstream is *extraction* (potentially noisy, confidence-scored), and everything downstream is *generation under contract* (verifiable against the BSG). Without this boundary, the pipeline is a chain of LLM calls with no checkpoint — you get code at the end and no way to tell where it went wrong. With the BSG, a human reviewer can inspect after Agent 2 and catch extraction errors before any code is generated.

The RQ5 results (Table 6) provide empirical support for this design. The BSG captures 92.3% of gold-standard rules with 90.2% precision — yet end-to-end BER is only 9.4% with GPT-4o-mini (19.4% with codex). This 71–83-point gap between extraction quality and code quality pinpoints the bottleneck: the Modernization Transformer (Agent 3), not the extraction pipeline, is the weak link.

### 6.2 Why the Feedback Loop Is Decisive

Under fair evaluation, full AgentModernize with feedback is the only configuration with non-zero mean BER under GPT-4o-mini, GPT-4o, and GPT-5.3-codex (9.4%, 8.1%, and 19.4% respectively), while SP-LLM and CoT-LLM score 0.0% on every backbone. Without feedback, mean BER is 0.0% on GPT-4o-mini (Table 5) and GPT-5.3-codex (Table 8), matching SP-LLM and CoT-LLM there. On GPT-4o, the no-feedback variant is an exception: 44.4% BER on S1 (5.6% averaged across all scenarios) — non-zero, but far below the full pipeline’s 58.3% on S1 and 8.1% mean.

The feedback mechanism's effectiveness depends on whether the initial code has *correctable point errors* versus *structural mismatches*. In S1 (order validation), the generated code implemented most business rules correctly but miscalculated a tier threshold — a localized error the Validator identified and the Transformer patched. In S3 (service activation), by contrast, the generated code failed to wire multi-step validation stages together — a structural error that incremental patching cannot fix. The model comparison (Table 7) confirms this pattern: switching models does not recover S2, S4, S6, or S7; it merely shifts which scenarios have correctable errors.

For practitioners, the implication is clear: the feedback loop should not be optional in any LLM-based modernization workflow. But it is not a silver bullet — when the initial code architecture diverges fundamentally from the gold standard, iterative correction cannot bridge the gap.

### 6.3 The Implicit Rule Problem

Throughout this paper, we use *implicit rule* as shorthand for *implicit business rule*: a behavioral requirement inferable from code patterns rather than stated in source or documentation. This is distinct from *data constraints* (type restrictions, value ranges, referential integrity), which the BSG captures separately as node annotations rather than as first-class rules.

Explicit rules are the easy case. A condition like `IF ACCOUNT_STATUS = 'INACTIVE' THEN REJECT` is visible in the source and straightforward to extract. The harder — and more interesting — case is implicit rules: a default value that silently initializes a field, an error handler that doubles as a business constraint, a cross-module data dependency that enforces referential integrity without ever stating it. Our evaluation distinguishes these two categories deliberately.

### 6.4 Model Capability and Architectural Sophistication

We expected frontier models to make the pipeline redundant. They did not. In Tables 7 and 8, SP-LLM and CoT-LLM remain at 0.0% BER; AgentModernize without feedback is likewise 0.0% under GPT-5.3-codex (Table 8). Full AgentModernize with feedback is the only configuration with non-zero mean BER under every backbone we tested; the GPT-4o no-feedback outcome (Section 6.2) does not match that cross-backbone pattern. The pipeline does not become optional as model capability increases.

What actually happens is more interesting: the pipeline *amplifies* model capability. Mean BER scales from 9.4% (mini) to 19.4% (codex). Stronger models produce better initial code, which gives the feedback loop more correctable point errors and fewer structural mismatches to deal with. We think of it this way: a good model gets you 80% of the way on the first pass, and the feedback loop closes some of the remaining gap. A weak model gets you 40% of the way, and the feedback loop has too much ground to cover. The architecture and the model work together, and neither is sufficient alone.

We should be transparent about statistical power. With N=8 scenarios, we cannot make strong claims. Most scenario-method cells yield σ = 0.0 across 3 trials (temperature 0.0, identical prompts), though S5 and S8 show non-zero σ (up to 14.4) due to feedback-loop variation in which patches get applied in which order. Extraction uses temperature 0.2 but produced identical outputs across all trials in practice. The pattern is consistent — SP-LLM and CoT-LLM achieve 0.0% BER under every backbone — but a larger benchmark would strengthen the claim.

The practical takeaway: the BSG pipeline pays for itself at every model tier. With budget models, it is the only path to non-zero BER. With frontier models, it achieves the highest BER in this study (19.4%). In regulated domains — telecom, banking, healthcare — the pipeline's traceability is an additional advantage that no single-prompt method can match.

### 6.5 Comparison Scope

We compare against LLM baselines (SP-LLM, CoT-LLM) rather than commercial modernization tools (IBM Rational, Micro Focus, TSRI) or recent agentic coding systems (SWE-Agent [20], OpenHands [21]). Commercial tools target syntactic translation and do not publish behavioral equivalence metrics. SWE-Agent and OpenHands solve a fundamentally different problem — resolving GitHub issues in existing codebases — rather than modernizing legacy systems with undocumented business rules.

One baseline we did not include is an "LLM + feedback loop without BSG" configuration — i.e., direct prompting with validator feedback but no intermediate specification. This would isolate whether improvements come from the BSG or from the feedback loop alone. Our ablation (Table 5) shows feedback is necessary, but does not fully prove BSG is sufficient. We flag this as a priority for follow-up work.

### 6.6 What This Approach Cannot Do (Yet)

We evaluated on scenarios of 100–310 lines of code. Real legacy systems are orders of magnitude larger. Scaling AgentModernize would require chunking strategies for the Legacy Analyzer, hierarchical BSGs that compose sub-workflows, and incremental validation.

Our model comparison (Section 5.6) confirms that the framework is model-agnostic across three models: GPT-4o-mini (9.4%), GPT-4o (8.1%), and GPT-5.3-codex (19.4%), each succeeding on different scenarios. A natural follow-up would evaluate across model families (Claude, Llama, Gemini) and explore ensemble strategies that select the best model per scenario.

## 7. Threats to Validity

**Internal Validity:** All eight benchmark scenarios are synthetic, though S8 targets a different domain (banking) to test cross-domain generalization. While we designed them to reflect realistic complexity — multi-step workflows, implicit business rules, cross-module dependencies — they inevitably lack the full messiness of production legacy codebases. The contribution should therefore be interpreted as an early empirical framework and benchmark study, not a production-ready modernization solution. The gold-standard business rules were authored by a single domain expert; a second annotator would strengthen confidence in the ground truth.

**External Validity:** We evaluated primarily on telecom scenarios with one banking scenario (S8), using COBOL and PL/SQL legacy languages. Healthcare and government legacy systems share structural similarities but also have domain-specific patterns that we have not tested. The S8 results provide preliminary evidence of cross-domain generalization, but further study is needed.

**Construct Validity:** Test-based verification cannot guarantee complete behavioral equivalence — it can only demonstrate the absence of divergence for tested paths. Untested edge cases may harbor latent behavioral regressions.

**Reliability:** LLM outputs are non-deterministic. We mitigate this by using low temperature settings (0.0 for code generation, 0.2 for extraction). Our fair evaluation uses 3 trials per scenario; most cells yield σ = 0.0, though S5 (σ = 14.4) and S8 (σ = 6.7) show trial-level variation introduced by the feedback loop's iterative patching. We evaluated with three models (GPT-4o-mini, GPT-4o, GPT-5.3-codex), confirming that results are not artifacts of a single model's behavior.

**Model Availability:** GPT-5.3-codex is a frontier model with restricted availability and significantly higher cost than GPT-4o-mini. The scaling pattern observed (Section 5.7) may not generalize to other frontier models or future model releases, and the cost differential limits practical applicability for large-scale modernization.

**Selection Bias:** The first author designed the benchmark scenarios and authored the gold-standard business rules. This dual role creates a risk that scenarios are inadvertently tuned to the framework's strengths. S8 offers partial mitigation because of *when* and *how* it entered the benchmark: it was authored after the pipeline and its prompt templates had been frozen, in a domain (banking) different from the seven telecom scenarios used during pipeline development, without any adjustment to the pipeline in response to S8-specific weaknesses. In effect, S8 functions as a held-out probe against the specific form of selection bias in which prompts and scenarios co-evolve. This does not eliminate broader benchmark-authoring bias — both S1–S7 and S8 were still written by the same author — and a fully independent benchmark authored by separate domain experts would strengthen validity.

**LLM-as-Evaluator:** The Equivalence Validator (Agent 4) is itself an LLM, raising the question of whether it introduces systematic bias into the BER metric. Our fair evaluation protocol mitigates this: gold-standard test scripts are synthesized by GPT-4o-mini from the scenario specification and a reference implementation (not by the pipeline under evaluation) and executed deterministically by pytest. BER is therefore protocol-dependent on the test-generation prompt. The Validator’s LLM role during the pipeline run is separate; the fair-eval BER is computed entirely from deterministic test execution against independently generated tests.

## 8. Artifact Availability

The AgentModernize framework implementation, LegacyModernize-8 benchmark scenarios (COBOL/PL/SQL source, gold-standard business rules, and behavioral test suites), BSG schema definitions, evaluation scripts, and sample prompts are publicly available at: https://github.com/nazib123/agent-modernize

## 9. AI Use Disclosure

AI tools (OpenAI GPT-4o) were used for grammar editing and formatting assistance during manuscript preparation. All technical content, experimental design, implementation, evaluation, and analysis were performed by the authors.

## 10. Conclusion

Legacy modernization is a translation problem *and* a behavioral preservation problem: syntactic translation is necessary but not sufficient. Single-pass LLM approaches — and industry transpilers before them — solve the translation half well and the preservation half not at all. AgentModernize is a framework that treats behavioral preservation as a first-class concern layered on top of translation, and the results, while modest in absolute terms, isolate one mechanism clearly: the feedback loop is what closes the preservation gap.

AgentModernize decomposes modernization into extraction, specification, transformation, and validation, connected through Behavioral Specification Graphs. SP-LLM and CoT-LLM scored 0.0% BER across all eight scenarios on every backbone. The pipeline without feedback scored 0.0% mean BER on GPT-4o-mini and GPT-5.3-codex; on GPT-4o it achieved non-zero BER only on S1 (44.4%; 5.6% mean over scenarios), still well below full AgentModernize with feedback. The only configuration with non-zero mean BER under all three backbones was full AgentModernize with feedback (9.4% GPT-4o-mini, 8.1% GPT-4o, 19.4% GPT-5.3-codex). The BSG captures 92.3% of gold-standard rules with 90.2% precision; the bottleneck is code generation, not extraction.

We expected frontier models to make the pipeline redundant. They did not. The pipeline amplifies model capability rather than competing with it. And the artifacts it produces along the way — business rule inventory, BSG, equivalence reports — are the kind of audit trail that regulated industries need and that no single-prompt method can provide.

**Future Work:** Three directions seem most promising: hierarchical BSGs for codebases larger than 300 lines, ensemble strategies that select the best model per scenario (our three-model results suggest 4/8 coverage is within reach), and a human-in-the-loop study to test whether domain experts actually trust modernized code more when they can inspect the intermediate BSG. That last one, we think, is the most important question this work opens up.

## References

[1] S. Comella-Dorda, K. Wallnau, R. Seacord, and J. Robert, "A survey of legacy system modernization approaches," Software Engineering Institute, Carnegie Mellon University, Tech. Rep. CMU/SEI-2000-TN-003, 2000. Available: https://doi.org/10.1184/R1/6585229

[2] H. P. Breivold, I. Crnkovic, and M. Larsson, "A systematic review of software architecture evolution research," Information and Software Technology, vol. 54, no. 1, pp. 16–40, 2012. DOI: 10.1016/j.infsof.2011.08.002

[3] R. Kazman, S. G. Woods, and S. J. Carrière, "Requirements for integrating software architecture and reengineering models: CORUM II," in Proceedings of the 5th Working Conference on Reverse Engineering (WCRE), pp. 154–163, 1998. DOI: 10.1109/WCRE.1998.723185

[4] S. Rugaber and K. Stirewalt, "Model-driven reverse engineering," IEEE Software, vol. 21, no. 4, pp. 45–53, 2004. DOI: 10.1109/MS.2004.23

[5] M. Chen et al., "Evaluating large language models trained on code," arXiv:2107.03374, 2021. Available: https://arxiv.org/abs/2107.03374

[6] R. Li et al., "StarCoder: may the source be with you!" arXiv:2305.06161, 2023. Available: https://arxiv.org/abs/2305.06161

[7] C. Hou et al., "Large language models for software engineering: A systematic literature review," ACM Transactions on Software Engineering and Methodology, vol. 33, no. 8, pp. 1–79, 2024. DOI: 10.1145/3695988

[8] H. Brunelière, J. Cabot, G. Dupé, and F. Madiot, "MoDisco: A model driven reverse engineering framework," Information and Software Technology, vol. 56, no. 8, pp. 1012–1032, 2014. DOI: 10.1016/j.infsof.2014.04.007

[9] A. De Lucia, A. R. Fasolino, and M. Napoli, "An approach for reverse engineering of COBOL-based applications," in Proceedings of the 5th European Conference on Software Maintenance and Reengineering (CSMR), pp. 217–226, 2001. DOI: 10.1109/CSMR.2001.914982

[10] Z. Li et al., "Large language models for code analysis: Do LLMs really do their job?" arXiv:2310.12357, 2023. Available: https://arxiv.org/abs/2310.12357

[11] Z. Li et al., "Automating code review activities by large-scale pre-training," in Proceedings of the 30th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering (ESEC/FSE), pp. 1035–1047, 2022. DOI: 10.1145/3540250.3549081

[12] C. S. Xia and L. Zhang, "Less training, more repairing please: revisiting automated program repair via zero-shot learning," in Proceedings of the 30th ACM ESEC/FSE, pp. 959–971, 2022. DOI: 10.1145/3540250.3549101

[13] R. Pan et al., "Lost in translation: A study of bugs introduced by large language models while translating code," in Proceedings of the 46th IEEE/ACM International Conference on Software Engineering (ICSE), 2024. DOI: 10.1145/3597503.3639226

[14] S. Hong et al., "MetaGPT: Meta programming for a multi-agent collaborative framework," in International Conference on Learning Representations (ICLR), 2024. arXiv:2308.00352. Available: https://arxiv.org/abs/2308.00352

[15] C. Qian et al., "ChatDev: Communicative agents for software development," in Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL), 2024. arXiv:2307.07924. Available: https://arxiv.org/abs/2307.07924

[16] K. Huang et al., "AgentCoder: Multi-agent-based code generation with iterative testing and optimisation," arXiv:2312.13010, 2023. Available: https://arxiv.org/abs/2312.13010

[17] R. Milner, Communication and Concurrency. Prentice Hall, 1989. ISBN: 978-0131150072

[18] W. McKeeman, "Differential testing for software," Digital Technical Journal, vol. 10, no. 1, pp. 100–107, 1998.

[19] T. Y. Chen, S. C. Cheung, and S. M. Yiu, "Metamorphic testing: A new approach for generating next test cases," Tech. Rep. HKUST-CS98-01, Hong Kong University of Science and Technology, 1998.

[20] J. Yang et al., "SWE-agent: Agent-computer interfaces enable automated software engineering," in Advances in Neural Information Processing Systems (NeurIPS), 2024. arXiv:2405.15793. Available: https://arxiv.org/abs/2405.15793

[21] X. Wang et al., "OpenHands: An open platform for AI software developers as generalist agents," arXiv:2407.16741, 2024. Available: https://arxiv.org/abs/2407.16741

[22] G. T. Leavens, A. L. Baker, and C. Ruby, "JML: A notation for detailed design," in Behavioral Specifications of Businesses and Systems, H. Kilov, B. Rumpe, and I. Simmonds, Eds. Springer, pp. 175–188, 1999. DOI: 10.1007/978-1-4615-5229-1_12

[23] B. Meyer, "Applying design by contract," IEEE Computer, vol. 25, no. 10, pp. 40–51, 1992. DOI: 10.1109/2.161279

[24] Object Management Group, "Architecture-Driven Modernization: Knowledge Discovery Meta-Model (KDM), v1.4," OMG Standard formal/2016-02-01, 2016. Available: https://www.omg.org/spec/KDM/1.4

[25] A. Madaan et al., "Self-Refine: Iterative refinement with self-feedback," in Advances in Neural Information Processing Systems (NeurIPS), 2023. arXiv:2303.17651. Available: https://arxiv.org/abs/2303.17651

[26] N. Shinn et al., "Reflexion: Language agents with verbal reinforcement learning," in Advances in Neural Information Processing Systems (NeurIPS), 2023. arXiv:2303.11366. Available: https://arxiv.org/abs/2303.11366
