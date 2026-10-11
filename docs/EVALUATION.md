# OM Search — Phase 3: Information Retrieval Evaluation Methodology

## 1. Mathematical Metric Definitions

Evaluation in OM Search follows formal Information Retrieval standards. All implementations are unit-tested and verified with hand-calculated test vectors in `backend/tests/test_evaluation_metrics.py`.

### 1.1 Precision at $k$ ($P@k$)
The fraction of retrieved documents in the top $k$ positions that are relevant (grade $\ge 1$):
$$P@k = \frac{\sum_{i=1}^{\min(k, |R|)} \mathbb{I}(\text{grade}(R_i) \ge 1)}{k}$$

### 1.2 Recall at $k$ ($R@k$)
The fraction of all known relevant documents that are retrieved in the top $k$:
$$R@k = \frac{\sum_{i=1}^{\min(k, |R|)} \mathbb{I}(\text{grade}(R_i) \ge 1)}{|\text{Relevant}|}$$

### 1.3 Reciprocal Rank ($RR$) and Mean Reciprocal Rank ($MRR$)
The reciprocal of the rank at which the *first* relevant document appears:
$$RR = \begin{cases} \frac{1}{\text{rank}_1} & \text{if a relevant document is found} \\ 0 & \text{otherwise} \end{cases}$$
$$MRR = \frac{1}{|Q|} \sum_{q \in Q} RR(q)$$

### 1.4 Average Precision ($AP$) and Mean Average Precision ($MAP$)
The mean of the precision scores calculated at the rank of each relevant retrieved document:
$$AP = \frac{\sum_{k=1}^{|R|} P@k \cdot \mathbb{I}(\text{grade}(R_k) \ge 1)}{|\text{Relevant}|}$$
$$MAP = \frac{1}{|Q|} \sum_{q \in Q} AP(q)$$

### 1.5 Discounted Cumulative Gain ($DCG@k$) and Normalized DCG ($NDCG@k$)
Evaluates graded relevance ($g_i \in \{0, 1, 2, 3\}$) with logarithmic position discounting:
$$DCG@k = \sum_{i=1}^{k} \frac{2^{g_i} - 1}{\log_2(i + 1)}$$
$$IDCG@k = \sum_{i=1}^{\min(k, |\text{Rel}|)} \frac{2^{g_{(i)}^*} - 1}{\log_2(i + 1)}$$
$$NDCG@k = \begin{cases} \frac{DCG@k}{IDCG@k} & \text{if } IDCG@k > 0 \\ 0 & \text{otherwise} \end{cases}$$

---

## 2. Benchmark Dataset Construction

The benchmark dataset is version-controlled in `backend/app/evaluation/dataset.py` (schema: `EvaluationDataset`, `QueryCase`):
- **Scale**: Graded relevance on a 4-point scale:
  - `3`: Highly relevant (Definitive answer or official documentation)
  - `2`: Relevant (Substantive, direct topical match)
  - `1`: Marginally relevant (Peripheral mention or broad overlap)
  - `0`: Irrelevant
- **Query Types**:
  - Technical: `fastapi python web framework`, `opensearch distributed search engine bm25`, `postgresql object relational database acid`.
  - Informational: `python programming language introduction`, `http response status codes`, `hypertext transfer protocol http overview`.
  - Navigational: `python`, `sqlite`, `postgresql docs`.
  - Freshness: `latest search engine updates 2024`.

---

## 3. Running Offline Evaluations

OM Search provides a command-line tool `scripts/evaluate_ranking.py` for evaluating ranking quality and generating reports:

### Single Evaluation
Evaluates the currently active production ranking pipeline:
```bash
python scripts/evaluate_ranking.py eval --out docs/experiments/evaluation_report.json
```

### Ablation Matrix Benchmark
Runs side-by-side evaluation across all 6 ranking variants and computes deltas:
```bash
python scripts/evaluate_ranking.py ablation --out docs/experiments/ablation_report.json
```
