# OM Search — Phase 3: Ranking Features and Signals

This document provides mathematical formulations, bounds, interpretation, and known failure modes for all signals in the OM Search ranking engine.

---

## 1. Feature Signal Reference Matrix

| Feature | Mathematical Definition | Raw Range | Normalized Range | Weight (Default) |
| :--- | :--- | :--- | :--- | :--- |
| **`bm25_norm`** | $s_i / (\max_{j \in C} s_j + \epsilon)$ | $[0, \infty)$ | $[0.0, 1.0]$ | 0.55 |
| **`title_coverage`** | $\frac{|\text{Terms}(q) \cap \text{Terms}(T)|}{|\text{Terms}(q)|}$ | $[0, 1]$ | $[0.0, 1.0]$ | 0.15 |
| **`exact_title_match`** | $\mathbb{I}(q_{\text{clean}} = T_{\text{clean}})$ | $\{0, 1\}$ | $\{0.0, 1.0\}$ | 0.05 |
| **`phrase_match`** | $\mathbb{I}(\text{phrase} \subseteq T) + 0.5 \cdot \mathbb{I}(\text{phrase} \subseteq B)$ | $[0, 1.5]$ | $[0.0, 1.0]$ | 0.05 |
| **`authority`** | $\frac{\log(1 + PR(d)) - \log(1 + PR_{\min})}{\log(1 + PR_{\max}) - \log(1 + PR_{\min}) + \epsilon}$ | $[0, 1]$ | $[0.0, 1.0]$ | 0.10 |
| **`freshness`** | $\exp(-\lambda \cdot \Delta t) \cdot \alpha(intent)$ | $[0, 1]$ | $[0.0, 1.0]$ | 0.05 |
| **`quality`** | $\min(1.0, \frac{\text{words}}{60}) \cdot (1 - 0.8 \cdot \text{spam})$ | $[0, 1]$ | $[0.0, 1.0]$ | 0.05 |
| **`spam_risk`** | Keyword stuffing penalty + repetition penalty | $[0, 1]$ | $[0.0, 1.0]$ | -0.15 |

---

## 2. In-Depth Signal Formulations

### 2.1 BM25 Candidate Relevance (`bm25_norm`)
- **Formula**:
  $$f_{\text{bm25}}(d, q) = \frac{\text{BM25Score}(d, q)}{\max_{k \in \text{Pool}} \text{BM25Score}(k, q) + 10^{-6}}$$
- **Rationale**: Raw BM25 scores vary wildly by query length and document IDF. Normalizing relative to pool maximum ensures comparability across heterogeneous queries.
- **Failure Mode**: When the entire candidate pool has weak lexical overlap, a low-relevance match can artificially scale to 1.0. Stage 1 thresholds mitigate this.

### 2.2 Title & Phrase Relevance (`title_coverage`, `phrase_match`)
- **Title Coverage**: Fraction of non-stopword query tokens present in the document title.
- **Exact Title Match**: Binary boost (+0.05) if the query exactly equals the cleaned document title (vital for navigational queries like `fastapi` or `python`).
- **Phrase Match**: Checks whether quoted phrases or multi-word n-grams occur contiguously in the title or content.

### 2.3 Link Authority (`authority`)
- **Formula**:
  Computed via offline PageRank iteration across the crawled web graph.
- **Log Scaling**: Raw PageRank obeys a power-law distribution. Log-scaling compresses extreme outliers and produces smooth gradients across mid-tier pages.
- **Failure Mode**: Newly crawled pages have an in-degree of 0 and receive the base minimum authority score ($0.15$). Handled gracefully without suppressing fresh documents.

### 2.4 Freshness Decay (`freshness`)
- **Formula**:
  $$f_{\text{fresh}}(d, q) = \exp\left(-\frac{\ln(2)}{T_{1/2}} \cdot \max(0, \Delta t)\right) \cdot \alpha(\text{intent})$$
- **Parameters**:
  - Half-life $T_{1/2} = 90$ days.
  - $\Delta t$: Age in days based on `published_at` or `indexed_at`.
  - Intent Multipliers $\alpha$:
    - Freshness intent: $1.0$
    - General/Informational: $0.4$
    - Technical/Documentation: $0.2$ (prevents old definitive documentation from being displaced by low-quality recent blog posts).
- **Clock Skew Protection**: Negative $\Delta t$ (dates in future) clamped to $\Delta t = 0$.

### 2.5 Content Quality & Anti-Spam (`quality`, `spam_risk`)
- **Text Length**: Smooth saturation reaching 1.0 at ~60 content words. Short stubs (< 8 words) receive a proportional brevity penalty.
- **Keyword Stuffing**: Detects terms whose occurrence ratio exceeds $18\%$ of total body words.
- **Title Repetition**: Detects documents that repeat title tokens excessively in low-word-count bodies.
- **Near-Duplicate Suppression**: 3-gram word shingles with Jaccard coefficient $\ge 0.70$ suppress mirror/reposted pages.

---

## 3. Configuration & Feature Weights

Configuration is managed via the version-controlled `RankingConfig` class (`backend/app/ranking/config.py`). Stage 1 limits, stage 2 weights, and feature toggles can be overridden at runtime or deployed as versioned ranking bundles.
