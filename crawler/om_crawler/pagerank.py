import logging
from typing import Dict, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)


class PageRankCalculator:
    """
    Deterministic, offline PageRank implementation supporting:
    - Directed hyperlink graphs.
    - Uniform redistribution of dangling node probability mass.
    - Configurable damping factor (default 0.85).
    - Configurable convergence tolerance (default 1e-6) and max iterations (default 100).
    - Numerical stability and score normalization.
    """

    def __init__(
        self,
        damping: float = 0.85,
        max_iterations: int = 100,
        tolerance: float = 1e-6,
    ):
        if not (0.0 < damping < 1.0):
            raise ValueError(f"Damping factor must be in (0, 1), got {damping}")
        self.damping = damping
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def compute(
        self,
        nodes: Set[str],
        edges: List[Tuple[str, str]],  # (source, target)
    ) -> Dict[str, float]:
        """
        Compute PageRank scores for the given node set and directed edge list.
        Returns a dictionary mapping node_id -> normalized PageRank score (sums to 1.0).
        """
        all_nodes = set(nodes)
        # Ensure any node mentioned in edges is in the node set
        for src, tgt in edges:
            all_nodes.add(src)
            all_nodes.add(tgt)

        num_nodes = len(all_nodes)
        if num_nodes == 0:
            return {}
        if num_nodes == 1:
            only_node = next(iter(all_nodes))
            return {only_node: 1.0}

        # Build adjacency structures (filter self-links and duplicate edges)
        out_edges: Dict[str, Set[str]] = {n: set() for n in all_nodes}
        in_edges: Dict[str, Set[str]] = {n: set() for n in all_nodes}

        for src, tgt in edges:
            if src == tgt:
                continue  # Ignore self-loops
            if src in all_nodes and tgt in all_nodes:
                out_edges[src].add(tgt)
                in_edges[tgt].add(src)

        # Initialize ranks uniformly: 1.0 / N
        initial_rank = 1.0 / num_nodes
        ranks: Dict[str, float] = {n: initial_rank for n in all_nodes}

        base_random_jump = (1.0 - self.damping) / num_nodes

        for iteration in range(1, self.max_iterations + 1):
            # Calculate dangling sum (mass from nodes with 0 outgoing links)
            dangling_mass = sum(
                ranks[n] for n in all_nodes if len(out_edges[n]) == 0
            )
            dangling_contrib = (self.damping * dangling_mass) / num_nodes

            next_ranks: Dict[str, float] = {}
            total_delta = 0.0

            for node in all_nodes:
                inbound_sum = sum(
                    ranks[pred] / len(out_edges[pred])
                    for pred in in_edges[node]
                )
                node_rank = base_random_jump + dangling_contrib + (self.damping * inbound_sum)
                next_ranks[node] = node_rank
                total_delta += abs(node_rank - ranks[node])

            ranks = next_ranks

            if total_delta < self.tolerance:
                logger.debug(
                    "PageRank converged at iteration %d with delta %.2e",
                    iteration, total_delta
                )
                break

        # Normalize final ranks to sum to 1.0
        total_sum = sum(ranks.values())
        if total_sum > 0:
            ranks = {n: round(r / total_sum, 8) for n, r in ranks.items()}

        return ranks
