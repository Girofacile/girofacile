"""Current offline quality/scaling benchmark entry point.

Historical 81f5121 reports remain archived in docs/optimizer-benchmark-results.json.
The current reference is the distance-first 824816f search, not a time-weighted score.
"""
from run_optimizer_scaling_benchmark import main

if __name__ == '__main__':
    main()
