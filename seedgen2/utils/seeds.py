# Get and process dynamic information from SeedD runtime
# The dynamic information includes:
# - coverage
# - predicates
# - call graph

class RunSeedInfo:
    def __init__(self, seed_path: str, coverage: float):
        self.seed_path = seed_path
        self.coverage = coverage
