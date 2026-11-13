"""V32.1 observation collector entry point."""
import argparse
from collectors.cwa_observation import main as collect_cwa


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["cwa"], default="cwa")
    args = parser.parse_args()
    if args.source == "cwa":
        collect_cwa()


if __name__ == "__main__":
    main()
