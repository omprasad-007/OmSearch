import pytest
from crawler.om_crawler.pagerank import PageRankCalculator


def test_pagerank_empty_graph():
    calc = PageRankCalculator()
    assert calc.compute(set(), []) == {}


def test_pagerank_single_node():
    calc = PageRankCalculator()
    ranks = calc.compute({"A"}, [])
    assert ranks == {"A": 1.0}


def test_pagerank_two_node_cycle():
    # Symmetric 2-node cycle: A <-> B
    calc = PageRankCalculator(damping=0.85)
    ranks = calc.compute({"A", "B"}, [("A", "B"), ("B", "A")])
    assert pytest.approx(ranks["A"], 0.001) == 0.5
    assert pytest.approx(ranks["B"], 0.001) == 0.5


def test_pagerank_three_node_star():
    # A -> B, A -> C, B -> C, C -> A
    # Inbound edges: C receives from A and B; B receives from A; A receives from C.
    calc = PageRankCalculator(damping=0.85)
    ranks = calc.compute({"A", "B", "C"}, [("A", "B"), ("A", "C"), ("B", "C"), ("C", "A")])

    # Node C has the highest in-degree and authority
    assert ranks["C"] > ranks["A"]
    assert ranks["C"] > ranks["B"]
    assert pytest.approx(sum(ranks.values()), 0.001) == 1.0


def test_pagerank_dangling_node_handling():
    # A -> B, B has no outgoing links (dangling)
    # Dangling mass must be redistributed without leaking rank mass
    calc = PageRankCalculator(damping=0.85)
    ranks = calc.compute({"A", "B"}, [("A", "B")])

    assert pytest.approx(sum(ranks.values()), 0.001) == 1.0
    # B receives all of A's outbound probability plus uniform dangling mass
    assert ranks["B"] > ranks["A"]


def test_pagerank_ignores_self_loops_and_duplicates():
    calc = PageRankCalculator(damping=0.85)
    # Self-loops A -> A and duplicate edge (A, B)
    edges = [("A", "A"), ("A", "B"), ("A", "B"), ("B", "A")]
    ranks = calc.compute({"A", "B"}, edges)

    assert pytest.approx(ranks["A"], 0.001) == 0.5
    assert pytest.approx(ranks["B"], 0.001) == 0.5
