# ModelMatch AI

### An Evidence-Grounded Multi-Agent System for LLM Selection

ModelMatch AI is an AI-powered model selection workspace that helps product managers, engineers, and technical decision-makers identify suitable large language models for real-world applications.

Instead of relying solely on general recommendations, ModelMatch AI combines model intelligence, task-specific capabilities, API pricing, and operational performance to support transparent, evidence-based decisions.


---


## 1. Overview

### The Problem

Choosing an LLM for a production application involves more than identifying the highest-performing model.

Different use cases require different capabilities, and practical decisions must account for several competing factors:

- **Model Quality:** How capable is the model overall?
- **Task Relevance:** How well does its measured performance align with the intended application?
- **Cost Efficiency:** What would the model cost under the expected workload?
- **Operational Performance:** Does its observed latency and output speed fit the application's needs?
- **Evidence Reliability:** Which claims are supported by available data, and which remain unverified?

General-purpose LLMs can suggest models, but their recommendations may rely on previously learned information rather than newly retrieved, model-specific evidence.

### Our Solution

ModelMatch AI transforms a natural-language product requirement into a structured model selection analysis.

The application provides:

| **Feature** | **What It Provides** |
| --- | --- |
| **Best Overall Recommendation** | The highest-ranked qualified model in the supported scoring cohort, when a complete score is available |
| **Ranked Model Comparison** | Raw Ranking with original and adjustable weights, plus side-by-side comparison of other scored models |
| **Potential Alternatives — Limited Evidence** | Unranked models with a known general or task-specific index and an unavailable composite score |
| **Evidence and Operational Tradeoffs** | G/U/O/S breakdown, estimated monthly token cost, mean latency, output speed, data sources, and qualification status |

ModelMatch shows a Best Overall recommendation only when an eligible model has enough evidence for a complete score. Recommendations use exact AA model entries, not model-family grouping or diversity rules. Raw Ranking preserves each eligible, fully scored entry; limited-evidence alternatives remain unranked.

### Target Users

**AI Product Managers** can compare quality, cost, and operational tradeoffs before selecting models for a product.

**AI Engineers** can evaluate API pricing, performance, and technical constraints before prototyping or deployment.

**Technical Decision-Makers** can review model recommendations together with their supporting evidence and limitations.


---


## 2. How It Works

ModelMatch AI follows a **Deep Research multi-agent architecture**, separating evidence collection, evaluation, and final recommendation.

### Research Agents

| **Agent**                               | **Responsibility**                                                                                                               |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| **Lead Agent**                          | Interprets user requirements, coordinates researchers, checks evidence, and requests bounded follow-up research when appropriate |
| **Researcher A — General Intelligence** | Retrieves general model capability measurements from Artificial Analysis                                                         |
| **Researcher B — Use-case Capability**  | Identifies task-relevant evaluation indices and assesses their relevance                                                         |
| **Researcher C — Operational Fit**      | Examines API pricing, response performance, workload assumptions, and operational constraints                                    |
| **Writer**                              | Produces a validated selection of recommendation and evidence references for the final report                                    |

Researchers execute in parallel with independent contexts. Their evidence is combined by the Lead and passed to deterministic decision tools.

The final report is assembled from validated selections and structured evidence, so the Writer cannot arbitrarily change model scores or rankings.

### Decision Methodology

ModelMatch uses an interpretable composite score:

[\
S = \alpha G + (1-\alpha)U + O\
]

Where:

- **G — General Intelligence:** Overall capability score from Artificial Analysis.
- **U — Use-case Capability:** Task-relevant capability score from Artificial Analysis, where available.
- **O — Operational Adjustment:** Deterministic adjustment based on supported cost and performance preferences.
- **α — General Capability Weight:** Controls the relative influence of general versus task-specific capability.

G and U retain their original index-point scales. The composite score is a **custom selection metric**, not an official Artificial Analysis benchmark or a prediction of real-world accuracy.

Users can adjust the weighting to explore how recommendations change without repeating the underlying research.

Missing benchmark values are not replaced with fabricated scores or dataset averages.


---


## 3. Example Queries & Model Comparisons

The following cases illustrate how ModelMatch AI approaches practical model selection problems.

The Gemini baseline summaries are condensed from responses provided by the project author. They describe what Gemini recommended, but the underlying specifications and benchmark claims were not independently verified in those baseline responses.

ModelMatch results are identified as either **recorded evaluation results** or **expected system behavior** where a complete historical response was not preserved.

### Case 1 — Financial Research Assistant

**User Prompt**

> I am building an AI-powered financial research assistant that analyzes financial reports, summarizes market trends, and generates investment research insights. I need a model with strong reasoning abilities and reliable financial domain knowledge. Recommend the top three LLMs.

|                       | **Gemini Baseline**                                                                                  | **ModelMatch AI**                                                                                   |
| ------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Best Overall**          | Claude Opus 5.5                                                                                      | **Claude Fable 5.2 (Max, Default Fallback)**                                                        |
| **Other models**          | Gemini 4 Carbon, Claude Fable 5.2, and other models for specific use cases                           | Compare other scored models in Raw Ranking and inspect unranked models with partial evidence where available                  |
| **Selection Basis**       | Financial reasoning, long-document capabilities, published benchmark claims, and cost considerations | Retrieved General Intelligence and Finance Capability indices, combined using a deterministic score |
| **Quantitative Evidence** | Cites benchmark rankings and pricing claims without live tool verification                           | G = 64.6; U = 64.7; O = 0; **S = 64.67**                                                            |
| **Evidence Limitations**  | Current accuracy of specifications is not established by the baseline                                | Flags unverified production specifications                 |

**What ModelMatch Adds**

Rather than selecting a model through general reasoning alone, ModelMatch produces a reproducible comparison using retrieved, task-relevant benchmark data.

Its Financial analysis selected Claude Fable 5.2 as the highest-scoring candidate under the recorded snapshot and weighting. The current interface presents that Best Overall choice alongside Raw Ranking and any limited-evidence alternatives.

**Expected Answer:** Identify the highest-scoring qualified Financial candidate based on available General Intelligence and Finance Capability evidence, with transparent scoring and limitations.

**Evidence Source:** Artificial Analysis Free API, `GET /api/v2/language/models/free`; fields `evaluations.artificial_analysis_intelligence_index` and `evaluations.artificial_analysis_finance_and_accounting_index`.


---


### Case 2 — E-commerce Shopping Assistant

**User Prompt**

> I am building an AI shopping assistant for an online retail platform. The assistant will answer product questions, compare specifications, and generate personalized shopping recommendations. I expect 100,000 requests per month, with an average of 2,000 input tokens and 500 output tokens per request. I prefer a model with a mean time to first token below 2 seconds and an estimated monthly API cost below $300. Recommend the top three LLMs, prioritizing instruction following, cost efficiency, and response speed. Clearly distinguish verified specifications from estimates.

|                      | **Gemini Baseline**                                                          | **ModelMatch AI — Expected Behavior**                                                   |
| ------------------------ | ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **Best Overall**         | Claude Haiku 5.5                                                             | Selects a qualified model only if sufficient task and operational evidence is available |
| **Other models**         | GPT-6 Luna and Gemini models                                                 | Compare estimated cost and mean TTFT across scored models and inspect any limited-evidence alternatives           |
| **Cost Analysis**        | Estimates $45/month for its preferred models using stated token prices       | Calculates monthly API cost from retrieved pricing and the specified workload           |
| **Latency Analysis**     | Claims sub-second TTFT for preferred models                                  | Compares retrieved mean TTFT with the 2-second preference                               |
| **Evidence Limitations** | Pricing and latency assumptions were not independently checked through tools | Separates measured data, estimates, unsupported task mappings, and missing metrics      |

**What ModelMatch Adds**

ModelMatch turns an operationally constrained product question into a quantitative model comparison.

For the specified workload, it can calculate:

- **Monthly input volume:** 200 million tokens
- **Monthly output volume:** 50 million tokens
- **Estimated cost:** 200 × input price per million + 50 × output price per million
- **Performance preference:** Mean TTFT below 2 seconds
- **Budget preference:** Estimated monthly cost below $300

The system evaluates the tradeoff between task suitability, cost, and latency rather than relying exclusively on general model reputation.

**Expected Answer:** Identify Best Overall when task-relevant evidence and workload-specific operational estimates support a qualified, fully scored model. Compare any other scored models in Raw Ranking.

**Evidence Source:** Artificial Analysis Free API, `GET /api/v2/language/models/free`; fields `pricing.price_1m_input_tokens`, `pricing.price_1m_output_tokens`, and `performance_v3` mean latency/speed metrics.


---


### Case 3 — Legal Document Analysis

**User Prompt**

> I am building an AI assistant for a legal research team. It needs to review long contracts, identify important clauses, compare multiple documents, and produce accurate summaries with references to the original text. The system must support input documents of at least 100,000 tokens. Recommend the top three LLMs that meet this requirement, and clearly identify any specifications that cannot be verified.

|                      | **Gemini Baseline**                                                     | **ModelMatch AI — Expected Behavior**                                                     |
| ------------------------ | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **Best Overall**         | Gemini 4 Carbon                                                         | No deployment-qualified recommendation without verified mandatory input-capacity evidence |
| **Other models**         | Claude Opus 5.5 and GPT-6.1 Sol                                         | Inspect limited-evidence models where available. Qualification still requires verified input capacity.                               |
| **Selection Basis**      | Legal reasoning benchmarks, reported context limits, and pricing        | General Intelligence, Legal Capability, and explicit hard-constraint checks               |
| **Context Requirement**  | Claims all three models satisfy the 100K-token requirement              | Does not assume that a reported combined context window proves maximum input capacity     |
| **Evidence Limitations** | Detailed provider specifications are asserted without live verification | Marks unsupported input-capacity requirements as **Unverified**, not satisfied            |

**What ModelMatch Adds**

This example highlights the importance of knowing when available data is insufficient.

For legal applications, a model can demonstrate strong benchmark performance while still lacking verified evidence for a mandatory technical requirement.

ModelMatch separates **model quality** from **deployment eligibility** and does not certify that a model satisfies a 100,000-token input requirement merely because its reported context window is large.

**Expected Answer:** Identify legal capability evidence where available, but refrain from certifying deployment-ready recommendations until the mandatory input-capacity specification has been verified.

**Evidence Source:** Artificial Analysis Free API, `GET /api/v2/language/models/free`; fields `evaluations.artificial_analysis_intelligence_index` and `evaluations.artificial_analysis_legal_index`. Verified input-capacity evidence would require appropriate official provider specifications.

**Evaluation Status:** The limitation-handling policy is supported by existing offline evidence. A complete matching historical live response has not been recovered.


---


## 4. Data Sources & Methodology

### Artificial Analysis

ModelMatch AI uses the [Artificial Analysis](https://artificialanalysis.ai/) Free API as its primary model evaluation source.

**Data access:** `GET https://artificialanalysis.ai/api/v2/language/models/free`

The backend retrieves paginated model records using a server-side API credential, preserves retrieval metadata, and associates evaluation fields with exact model IDs. No proprietary snapshot is required in the public repository to understand the data-loading process.

| **Data Category**          | **Purpose**                        |
| -------------------------- | ---------------------------------- |
| General Intelligence Index | Overall model capability evidence  |
| Capability Indices         | Task-relevant model performance    |
| Input/Output Pricing       | API cost estimation                |
| Mean TTFT                  | Response initiation performance    |
| Mean Output Speed          | Generation throughput              |
| Model Identity & Version   | Evidence matching and traceability |

See the [Artificial Analysis API Documentation](https://artificialanalysis.ai/data-api/docs) and [Capability Index Methodology](https://artificialanalysis.ai/methodology/capability-indices).

### Evidence-Grounded Decisions

ModelMatch distinguishes between:

- **Fully evaluable:** Sufficient evidence exists to compute the composite score.
- **Provisional:** Some evidence supports further consideration, but the full ranking is not established.
- **Unverified:** A mandatory requirement cannot be confirmed using available evidence.
- **Ineligible:** A known hard requirement is violated.

This separation prevents incomplete benchmark coverage from being silently treated as proof of model suitability.


---


## 5. Live Demo & Usage

**Application:** [Launch ModelMatch AI](https://modelmatch-agent-git-978311583991.europe-west1.run.app/)

### How to Use

1. Describe the application you are building and the task the LLM should perform.
2. Optionally specify your expected workload, monthly budget, latency preferences, or technical requirements.
3. Run the analysis to view the research process and model comparison.
4. Explore recommended candidates, score breakdowns, and supporting evidence.
5. Adjust the General Intelligence weight to examine how model selection changes.

The interface includes Overview, Comparison, Evidence, and model-detail views.

### API Compatibility

ModelMatch provides a Project 1-compatible `/chat` endpoint.


---


## 6. Limitations

ModelMatch AI is a decision-support system, not an independent LLM benchmarking service.

- **Incomplete Benchmark Coverage:** Not every model has available General Intelligence and task-specific Capability scores.
- **Snapshot Dependence:** Model rankings and prices may change as source data is updated.
- **Operational Uncertainty:** Average latency does not guarantee tail latency or production service levels.
- **Unverified Specifications:** Context capacity, deployment availability, and residency requirements may require independent official verification.
- **Custom Decision Policy:** Composite scores and weighting choices represent a transparent selection heuristic, not a validated measure of real-world performance.

The system prioritizes traceability and explicit uncertainty over unsupported recommendations. Final model choices should be validated with application-specific benchmarks and production testing.
