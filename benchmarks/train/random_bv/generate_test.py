from benchmarks.train.random_bv.generate import Spec, compile_eqfob, gen_eqfob
from core.formula import Formula


def test_gen_eqfob_compiles() -> None:
    for mode, nc in [("under", 1), ("mixed", 3), ("over", 6)]:
        spec = Spec(width=2, n_funs=2, n_forall=2, n_constraints=nc, seed=42, mode=mode)
        src = gen_eqfob(spec)
        assert "fun f0" in src and "forall x0" in src
        f = compile_eqfob(src, width=2)
        assert isinstance(f, Formula)
        assert f.n_vars > 0
        assert len(f.clauses) > 0
        assert f.universals
        assert f.dependencies


def test_determinism() -> None:
    spec = Spec(width=2, n_funs=1, n_forall=1, n_constraints=2, seed=7, mode="mixed")
    assert gen_eqfob(spec) == gen_eqfob(spec)
