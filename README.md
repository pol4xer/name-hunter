# Name Hunter

Проверка доступности Telegram username через Telethon. Работает с личным
Telegram-аккаунтом и сохраняет результаты каждого прохода в CSV и текстовые файлы.

## Установка

Нужен Python 3.11 или новее. После клонирования репозитория откройте терминал
в папке проекта и создайте локальное окружение.

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
cp config.example.toml config.toml
cp candidates.example.txt candidates.txt
```

Windows (PowerShell):

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.example.toml config.toml
Copy-Item candidates.example.txt candidates.txt
```

В локальном `config.toml` заполните `telegram.api_id` и `telegram.api_hash`
данными своего приложения с [my.telegram.org/apps](https://my.telegram.org/apps).
В `candidates.txt` замените примеры своими именами: одно имя на строку,
с `@` или без него. Шаблоны с суффиксом `.example` оставляйте без личных данных.

## Запуск из IDE

1. Откройте папку проекта `name-hunter`.
2. Выберите созданное окружение: `.venv/bin/python` на macOS / Linux или
   `.venv\Scripts\python.exe` на Windows. В VS Code используйте команду
   **Python: Select Interpreter**, в PyCharm — настройки интерпретатора проекта.
3. Откройте `main.py` и нажмите **Run** в консоли с поддержкой ввода.
   Аргументы запуска и переменные окружения не нужны.

При первой авторизации в консоли потребуется ввести телефон, код подтверждения
и пароль 2FA, если он включён. Сессия сохраняется локально для следующих запусков;
если Telegram её отзовёт, потребуется авторизоваться снова.

Из терминала проект запускается командой `.venv/bin/python main.py`
(на Windows — `.venv\Scripts\python.exe main.py`).

## Настройки

Все параметры находятся в `config.toml`:

| Раздел | Параметр | Назначение |
| --- | --- | --- |
| `telegram` | `api_id`, `api_hash` | Данные приложения Telegram |
| `telegram` | `session_file` | Путь сохранённой авторизации, по умолчанию `data/username_checker` |
| `checker` | `candidates_file` | Файл со списком имён |
| `checker` | `delay` | Пауза между запросами; минимум 0.5 секунды |
| `checker` | `interval` | `0` — один проход; положительное число — повтор с паузой минимум 300 секунд |
| `checker` | `results_dir` | Каталог результатов |

Относительные пути считаются от папки конфигурации, поэтому рабочая папка IDE
не влияет на запуск. Пустые строки, комментарии с `#` и повторяющиеся имена
пропускаются. Имена приводятся к нижнему регистру.

## Результаты

Каждый проход создаёт каталог `results/YYYY-MM-DD_HH-MM-SS/`:

- `results.csv` — все проверенные имена, статус и пояснение;
- `available.txt` — доступные для свободной регистрации;
- `fragment.txt` — доступные только для покупки на Fragment;
- `occupied.txt` — занятые.

Другие статусы: `INVALID`, `UNKNOWN`, `FLOOD_WAIT`, `ERROR`. При ограничении
Telegram скрипт выдерживает паузу; при ожидании свыше 120 секунд завершает
текущий проход. В режиме повторения следующий проход начинается не раньше
истечения указанного Telegram ожидания, даже если `interval` меньше него.
Успешная проверка имени не регистрирует его.

## Структура

```text
main.py                    # Запуск из IDE
config.toml                # Локальные данные приложения и настройки (вне Git)
config.example.toml        # Шаблон без секретов
candidates.txt             # Ваш список (вне Git)
candidates.example.txt     # Пример формата
name_hunter/
  config.py                # Чтение и проверка настроек
  checker.py               # Запросы к Telegram и сохранение результатов
data/                      # Сессия Telegram (вне Git)
results/                   # Результаты (вне Git)
tests/                     # Проверки без обращения к Telegram
.github/workflows/ci.yml    # Автоматические проверки push и pull request
pyproject.toml             # Метаданные и зависимости
.venv/                     # Локальное окружение Python
```

`config.toml`, Telegram-сессии, личный список имён, результаты и виртуальное
окружение исключены через `.gitignore` и создаются только локально. Не добавляйте
их принудительно через `git add -f`. Если меняете пути в конфиге, добавьте новые
пути с личными данными в `.gitignore` до коммита. Файл сессии предоставляет доступ
к аккаунту: не публикуйте его или содержимое конфига в PR, issues и логах.

## Проверки

```sh
.venv/bin/python -m unittest discover -s tests -v
```

На Windows используйте `.venv\Scripts\python.exe` вместо `.venv/bin/python`.
Для тестов не нужны `config.toml`, `candidates.txt` или авторизация Telegram:
они используют временные каталоги и подменяют сетевые вызовы. GitHub Actions
устанавливает проект и запускает эти же проверки на Python 3.11 и 3.14 при push
и открытии или обновлении pull request.
