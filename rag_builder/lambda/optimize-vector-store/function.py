from optimizer import LanceDbOptimizer


def handler(*_) -> None:
    LanceDbOptimizer().optimize()
