def test_package_imports() -> None:
    import benchmarks.runner
    import provers.forkres
    import tools.eqfob
    import tools.verify

    assert provers.forkres
    assert tools.eqfob
    assert tools.verify
    assert benchmarks.runner
