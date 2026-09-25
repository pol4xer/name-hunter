"""Загрузка настроек Name Hunter из TOML без побочных эффектов."""

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    api_id: int = field(repr=False)
    api_hash: str = field(repr=False)
    candidates_file: Path
    delay: float
    interval: int
    session_file: Path
    results_dir: Path


def _section(data: dict, name: str, *, required: bool = False) -> dict:
    if name not in data:
        if required:
            raise ValueError(f"В config.toml отсутствует раздел [{name}].")
        return {}
    section = data[name]
    if not isinstance(section, dict):
        raise ValueError(f"Раздел [{name}] должен быть таблицей TOML.")
    return section


def _path(section: dict, name: str, default: str, base_dir: Path) -> Path:
    value = section.get(name, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Параметр {name} должен быть непустой строкой с путём.")
    try:
        return (base_dir / Path(value).expanduser()).resolve()
    except (OSError, RuntimeError, ValueError):
        raise ValueError(f"Не удалось определить путь для параметра {name}.") from None


def load_config(path: str | Path = PROJECT_DIR / "config.toml") -> Config:
    """Прочитать настройки; относительные пути считаются от файла конфигурации."""
    try:
        config_path = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("Не удалось определить путь к файлу конфигурации.") from None

    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(
            f"Не найден файл конфигурации: {config_path}. "
            "Скопируйте config.example.toml в config.toml и заполните настройки."
        ) from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        # Ошибки TOML могут содержать исходные значения; не выводим их вместе с ключами.
        raise ValueError(
            f"Некорректный TOML в файле: {config_path}. "
            "Проверьте формат по config.example.toml."
        ) from None
    except OSError:
        raise ValueError(
            f"Не удалось прочитать файл конфигурации: {config_path}."
        ) from None

    telegram = _section(data, "telegram", required=True)
    checker = _section(data, "checker")

    api_id = telegram.get("api_id")
    api_hash = telegram.get("api_hash")
    if type(api_id) is not int or api_id <= 0:
        raise ValueError("Укажите положительный целый telegram.api_id в config.toml.")
    if not isinstance(api_hash, str) or not api_hash.strip():
        raise ValueError("Заполните telegram.api_hash непустой строкой в config.toml.")

    delay = checker.get("delay", 1.0)
    if type(delay) not in (int, float):
        raise ValueError(
            "Параметр checker.delay должен быть конечным числом не меньше 0."
        )
    try:
        delay = float(delay)
    except OverflowError:
        raise ValueError(
            "Параметр checker.delay должен быть конечным числом не меньше 0."
        ) from None
    if not math.isfinite(delay) or delay < 0:
        raise ValueError(
            "Параметр checker.delay должен быть конечным числом не меньше 0."
        )

    interval = checker.get("interval", 0)
    if type(interval) is not int or interval < 0:
        raise ValueError(
            "Параметр checker.interval должен быть целым числом не меньше 0."
        )

    return Config(
        api_id=api_id,
        api_hash=api_hash.strip(),
        candidates_file=_path(
            checker, "candidates_file", "candidates.txt", config_path.parent
        ),
        delay=delay,
        interval=interval,
        session_file=_path(
            telegram, "session_file", "data/username_checker", config_path.parent
        ),
        results_dir=_path(checker, "results_dir", "results", config_path.parent),
    )
