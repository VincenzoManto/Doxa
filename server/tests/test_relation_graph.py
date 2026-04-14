from relations.RelationGraph import RelationGraph  # type: ignore[import]


def test_init_from_yaml_loads_explicit_relations_and_keeps_lazy_neutral_defaults():
    graph = RelationGraph()
    graph.init_from_yaml(
        [
            {"source": "alice", "target": "bob", "trust": 0.8, "type": "ally"},
        ],
        ["alice", "bob", "carol"],
    )

    assert graph.get_trust("alice", "bob") == 0.8
    assert graph.get_rel_type("alice", "bob") == "ally"
    assert graph.get_trust("bob", "alice") == 0.5
    assert graph.get_rel_type("bob", "alice") == "neutral"


def test_update_trust_creates_missing_edges_and_reclassifies_labels():
    graph = RelationGraph()

    graph.update_trust("alice", "bob", 0.3)
    assert graph.get_trust("alice", "bob") == 0.8
    assert graph.get_rel_type("alice", "bob") == "ally"

    graph.update_trust("alice", "carol", -0.15)
    assert graph.get_trust("alice", "carol") == 0.35
    assert graph.get_rel_type("alice", "carol") == "rival"

    graph.update_trust("alice", "dave", -0.3)
    assert graph.get_trust("alice", "dave") == 0.2
    assert graph.get_rel_type("alice", "dave") == "enemy"


def test_update_trust_clamps_values_to_unit_interval():
    graph = RelationGraph()

    graph.update_trust("alice", "bob", 2.0)
    graph.update_trust("carol", "dave", -2.0)

    assert graph.get_trust("alice", "bob") == 1.0
    assert graph.get_trust("carol", "dave") == 0.0


def test_decay_all_moves_values_toward_neutral_without_overshooting():
    graph = RelationGraph()
    graph.init_from_yaml(
        [
            {"source": "alice", "target": "bob", "trust": 0.9, "type": "ally"},
            {"source": "bob", "target": "alice", "trust": 0.2, "type": "enemy"},
        ],
        ["alice", "bob"],
    )

    graph.decay_all(0.25)
    assert graph.get_trust("alice", "bob") == 0.65
    assert graph.get_trust("bob", "alice") == 0.45

    graph.decay_all(0.25)
    assert graph.get_trust("alice", "bob") == 0.5
    assert graph.get_trust("bob", "alice") == 0.5


def test_to_list_serializes_relation_records_with_rounded_trust():
    graph = RelationGraph()
    graph.init_from_yaml(
        [
            {"source": "alice", "target": "bob", "trust": 0.67891, "type": "neutral"},
        ],
        ["alice", "bob"],
    )

    assert graph.to_list() == [
        {"source": "alice", "target": "bob", "trust": 0.6789, "type": "neutral"}
    ]