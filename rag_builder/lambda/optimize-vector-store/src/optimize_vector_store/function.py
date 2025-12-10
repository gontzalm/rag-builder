from optimize_vector_store.optimizer import LanceDbOptimizer


def handler(*_) -> None:
    LanceDbOptimizer().optimize()
