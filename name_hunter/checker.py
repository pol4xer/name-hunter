#!/usr/bin/env python3
"""Проверка доступности Telegram username и сохранение результатов."""

import asyncio
import csv
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, errors, functions

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DELAY = 1.0


def load_usernames(path: str | Path) -> list[str]:
    result = []
    seen = set()

    for line in Path(path).read_text(encoding="utf-8").splitlines():
        username = line.strip()

        if not username or username.startswith("#"):
            continue

        if username.startswith("@"):
            username = username[1:]

        username = username.strip().lower()

        if username and username not in seen:
            seen.add(username)
            result.append(username)

    return result


def classify_rpc_error(exc: Exception) -> tuple[str, str]:
    name = type(exc).__name__
    message = getattr(exc, "message", "")
    raw = f"{name} {message} {exc}".upper()

    if "USERNAME_PURCHASE_AVAILABLE" in raw:
        return "FRAGMENT", "Available only for purchase on Fragment"

    if "USERNAME_OCCUPIED" in raw:
        return "OCCUPIED", "Already occupied"

    if "USERNAME_INVALID" in raw:
        return "INVALID", "Invalid Telegram username"

    return "ERROR", str(exc)


async def check_username(client: TelegramClient, username: str):
    try:
        result = await client(functions.account.CheckUsernameRequest(username=username))

        if result:
            return {
                "username": username,
                "status": "AVAILABLE",
                "detail": "Free registration",
            }

        return {
            "username": username,
            "status": "UNKNOWN",
            "detail": "Telegram returned False",
        }

    except errors.UsernameOccupiedError:
        return {
            "username": username,
            "status": "OCCUPIED",
            "detail": "Already occupied",
        }

    except errors.UsernameInvalidError:
        return {
            "username": username,
            "status": "INVALID",
            "detail": "Invalid username",
        }

    except errors.FloodWaitError as exc:
        return {
            "username": username,
            "status": "FLOOD_WAIT",
            "detail": f"Wait {exc.seconds} seconds",
            "wait": exc.seconds,
        }

    except errors.RPCError as exc:
        status, detail = classify_rpc_error(exc)

        return {
            "username": username,
            "status": status,
            "detail": detail,
        }

    except Exception as exc:
        return {
            "username": username,
            "status": "ERROR",
            "detail": repr(exc),
        }


def save_results(
    results: list[dict],
    results_dir: str | Path = BASE_DIR / "results",
):
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    out = Path(results_dir) / stamp
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / "results.csv"

    with csv_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "username",
                "status",
                "detail",
            ],
        )

        writer.writeheader()

        for item in results:
            writer.writerow(
                {
                    "username": item["username"],
                    "status": item["status"],
                    "detail": item["detail"],
                }
            )

    available = [x["username"] for x in results if x["status"] == "AVAILABLE"]

    fragment = [x["username"] for x in results if x["status"] == "FRAGMENT"]

    occupied = [x["username"] for x in results if x["status"] == "OCCUPIED"]

    (out / "available.txt").write_text(
        "\n".join(available),
        encoding="utf-8",
    )

    (out / "fragment.txt").write_text(
        "\n".join(fragment),
        encoding="utf-8",
    )

    (out / "occupied.txt").write_text(
        "\n".join(occupied),
        encoding="utf-8",
    )

    return out


async def run_check(
    client: TelegramClient,
    usernames: list[str],
    delay: float,
):
    results = []

    total = len(usernames)

    for index, username in enumerate(usernames, 1):
        result = await check_username(client, username)

        status = result["status"]

        if status == "AVAILABLE":
            marker = "FREE    "
        elif status == "FRAGMENT":
            marker = "FRAGMENT"
        elif status == "OCCUPIED":
            marker = "TAKEN   "
        elif status == "INVALID":
            marker = "INVALID "
        else:
            marker = status[:8].ljust(8)

        print(f"[{index:>3}/{total}] {marker}  @{username}")

        results.append(result)

        # Если Telegram прямо потребовал подождать,
        # не пытаемся обходить ограничение.
        if status == "FLOOD_WAIT":
            seconds = int(result.get("wait", 0))

            if seconds > 120:
                print(f"\nTelegram requested a {seconds}s wait. Stopping this pass.")
                break

            print(f"Waiting {seconds}s...")
            await asyncio.sleep(seconds + 1)

        else:
            await asyncio.sleep(delay)

    return results


async def main(
    *,
    api_id: int,
    api_hash: str,
    candidates_file: str | Path = "candidates.txt",
    delay: float = DEFAULT_DELAY,
    interval: int = 0,
    session_file: str | Path = "username_checker",
    results_dir: str | Path = "results",
):
    """Запускает проверку с параметрами из Python, без аргументов терминала."""
    try:
        api_id = int(api_id)
    except (TypeError, ValueError):
        raise SystemExit("Укажите числовой telegram.api_id в config.toml.") from None

    if api_id <= 0 or not api_hash or not api_hash.strip():
        raise SystemExit(
            "Заполните telegram.api_id и telegram.api_hash в config.toml. "
            "Получить их можно на https://my.telegram.org/apps."
        )

    # Относительные пути считаются от корня проекта, независимо от рабочей папки IDE.
    candidates_path = BASE_DIR / Path(candidates_file).expanduser()
    session_path = BASE_DIR / Path(session_file).expanduser()
    output_path = BASE_DIR / Path(results_dir).expanduser()

    try:
        usernames = load_usernames(candidates_path)
    except OSError as exc:
        raise SystemExit(
            f"Не удалось прочитать список username: {candidates_path}\n{exc}"
        ) from None

    if not usernames:
        raise SystemExit(f"В файле нет username для проверки: {candidates_path}")

    print(f"Loaded {len(usernames)} usernames.\n")

    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash.strip())

    try:
        # При первом запуске в консоли IDE запрашиваются телефон, код и 2FA.
        # После авторизации используется сохранённая сессия.
        await client.start()

        while True:
            print("\n" + "=" * 60)
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            print("=" * 60)

            results = await run_check(
                client,
                usernames,
                max(delay, 0.5),
            )

            output_dir = save_results(results, output_path)

            free_count = sum(x["status"] == "AVAILABLE" for x in results)

            fragment_count = sum(x["status"] == "FRAGMENT" for x in results)

            occupied_count = sum(x["status"] == "OCCUPIED" for x in results)

            print()
            print(f"FREE:     {free_count}")
            print(f"FRAGMENT: {fragment_count}")
            print(f"OCCUPIED: {occupied_count}")
            print(f"Results:  {output_dir}")

            if interval <= 0:
                break

            repeat_interval = max(interval, 300)
            # Долгое ограничение завершает проход без ожидания внутри run_check.
            # Повтор не должен начинаться раньше разрешённого Telegram срока.
            if results and results[-1]["status"] == "FLOOD_WAIT":
                flood_wait = int(results[-1].get("wait", 0))
                if flood_wait > 120:
                    repeat_interval = max(repeat_interval, flood_wait + 1)

            print(f"\nNext check in {repeat_interval} seconds.")

            await asyncio.sleep(repeat_interval)

    finally:
        await client.disconnect()
