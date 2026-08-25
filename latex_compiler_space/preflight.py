"""Fail-closed egress preflight used before a per-job compiler service starts."""

from latex_compiler_space.app import verify_network_isolation


def main() -> int:
    verify_network_isolation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
