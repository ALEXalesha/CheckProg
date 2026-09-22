"""Снимки окна для README: собираются программой, а не руками.

    .venv\\Scripts\\python tools\\make_screenshots.py

Скрипт делает временный список, открывает его в настоящем окне и снимает виджет через
QWidget.grab() - в светлой и в тёмной теме. Снимок области экрана не годится: окно может
оказаться позади других, и в кадр попадёт чужое содержимое.

Настройки берутся во временную папку, поэтому ни settings.json, ни «последний открытый
файл» у пользователя не меняются.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
sys.path.insert(0, str(ROOT))

from checkprog.app import create_app  # noqa: E402
from checkprog.settings import Paths  # noqa: E402
from checkprog.window import MainWindow  # noqa: E402

LIST = {
    "version": 1,
    "items": [
        {"text": "Собрать рюкзак", "done": True},
        {"text": "Зарядить наушники и павербанк", "done": True},
        {"text": "Распечатать посадочный", "done": False,
         "note": "Два экземпляра: один в рюкзак, один в чемодан."},
        {"text": "Полить цветы", "done": False},
        {"text": "Проверить окна и воду", "done": False},
        {"text": "Взять зарядку для ноутбука", "done": False},
        {"text": "Скачать карты офлайн", "done": False},
        {"text": "Оплатить парковку у вокзала", "done": False,
         "note": "Приложение «Парковки», зона 412, на трое суток."},
        {"text": "Предупредить соседей", "done": False},
    ],
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="checkprog-shots-") as tmp:
        list_path = os.path.join(tmp, "Поездка.json")
        with open(list_path, "w", encoding="utf-8") as f:
            json.dump(LIST, f, ensure_ascii=False)

        paths = Paths(settings_file=os.path.join(tmp, "settings.json"),
                      lists_dir=tmp, portable=True)
        app = create_app()
        win = MainWindow(paths, list_path)
        win.resize(620, 560)
        win.show()
        app.processEvents()

        # Комментарий виден только у раскрытого пункта - раскрываем третий и встаём на него.
        win.toggle_expanded(2)
        win.select(2)
        app.processEvents()

        for mode, name in (("light", "window-light.png"), ("dark", "window-dark.png")):
            # set_theme_mode, а не theme.apply_mode: окно само перекрашивает свои
            # виджеты и отмечает пункт меню, иначе часть цветов останется от старой темы.
            win.set_theme_mode(mode)
            for _ in range(5):
                app.processEvents()
            shot = OUT / name
            win.grab().save(str(shot))
            print(f"  {name} ({shot.stat().st_size // 1024} КБ)")

        win.close()
    print(f"Готово: {OUT}")


if __name__ == "__main__":
    main()
