from tools.verify.formats import load_proof, parse_aag, parse_dqdimacs


def test_parse_dqdimacs() -> None:
    f = parse_dqdimacs("c hi\np cnf 4 2\na 1 2 0\nd 3 1 0\nd 4 2 0\n3 4 0\n-3 -4 0\n")
    assert f.n_vars == 4
    assert f.universals == (1, 2)
    assert f.dependencies == {3: frozenset({1}), 4: frozenset({2})}
    assert frozenset({3, 4}) in f.clauses


def test_parse_dqdimacs_e_line() -> None:
    f = parse_dqdimacs("p cnf 4 0\na 1 0\ne 3 0\na 2 0\ne 4 0\n")
    assert f.dependencies[3] == {1}
    assert f.dependencies[4] == {1, 2}


def test_parse_aag() -> None:
    aig = parse_aag("aag 3 2 0 1 1\n2\n4\n6\n6 2 4\ni0 u1\ni1 u2\no0 e3\n")
    assert aig.inputs == [2, 4]
    assert aig.outputs == [6]
    assert aig.gates == [(6, 2, 4)]
    assert aig.output_by_name("e3") == 6
    assert aig.cone_inputs(6) == {2, 4}


def test_load_proof(tmp_path) -> None:
    p = tmp_path / "p.frp"
    p.write_text('[{"clause":[1],"rule":"axiom"}]')
    pr = load_proof(p)
    assert len(pr.steps) == 1
    assert pr.steps[0].rule == "axiom"
