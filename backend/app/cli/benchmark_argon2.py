from __future__ import annotations

import argparse
import json
import platform
import resource
import statistics
import time

from app.modules.identity.passwords import PASSWORD_HASHER


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the configured Argon2id parameters")
    parser.add_argument("--samples", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.samples <= 100:
        parser.error("--samples must be between 1 and 100")
    password = "ClientOps benchmark only 2026"
    warmup = PASSWORD_HASHER.hash(password)
    PASSWORD_HASHER.verify(warmup, password)
    hash_samples: list[float] = []
    verify_samples: list[float] = []
    for _ in range(args.samples):
        started = time.perf_counter()
        encoded = PASSWORD_HASHER.hash(password)
        hash_samples.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        PASSWORD_HASHER.verify(encoded, password)
        verify_samples.append((time.perf_counter() - started) * 1000)

    def summary(samples: list[float]) -> dict[str, float]:
        return {
            "min": round(min(samples), 3),
            "median": round(statistics.median(samples), 3),
            "max": round(max(samples), 3),
        }

    print(
        json.dumps(
            {
                "environment": platform.platform(),
                "parameters": {
                    "algorithm": "argon2id",
                    "memory_cost_kib": 65536,
                    "time_cost": 3,
                    "parallelism": 4,
                    "salt_len": 16,
                    "hash_len": 32,
                },
                "warmup_samples": 1,
                "measured_samples": len(hash_samples),
                "hash_milliseconds": summary(hash_samples),
                "verify_milliseconds": summary(verify_samples),
                "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
