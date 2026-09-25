"""Запуск Name Hunter из IDE: откройте этот файл и нажмите Run."""

import asyncio
from dataclasses import asdict

from name_hunter.checker import main as run_check
from name_hunter.config import load_config


def main() -> None:
    try:
        config = load_config()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None

    try:
        asyncio.run(run_check(**asdict(config)))
    except KeyboardInterrupt:
        print("\nПроверка остановлена.")


if __name__ == "__main__":
    main()
