import json
import os
import tempfile
from dataclasses import dataclass, replace

FORMAT_VERSION = 1


class ChecklistFormatError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    text: str
    done: bool = False
    note: str = ""


_SURROGATES = {cp: None for cp in range(0xD800, 0xE000)}


def clean_text(text):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    # Tk 8.6 stores emoji as two UTF-16 halves; deleting one half leaves surrogate
    # code points that cannot be encoded as UTF-8 when saving.
    text = text.translate(_SURROGATES)
    return " ".join(text.splitlines()).replace("\t", " ").strip()


def clean_note(text):
    if not isinstance(text, str):
        raise TypeError("note must be a string")
    return "\n".join(text.translate(_SURROGATES).splitlines()).strip()


def _parse(data):
    if not isinstance(data, dict):
        raise ChecklistFormatError("ожидался JSON-объект")
    version = data.get("version", FORMAT_VERSION)
    if type(version) is not int:
        raise ChecklistFormatError("поле version должно быть целым числом")
    if version > FORMAT_VERSION:
        raise ChecklistFormatError(
            f"файл создан более новой версией программы (формат {version})")
    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ChecklistFormatError("нет списка items")
    items = []
    for n, raw in enumerate(raw_items, 1):
        if not isinstance(raw, dict) or not isinstance(raw.get("text"), str):
            raise ChecklistFormatError(f"пункт {n}: нет текста")
        done = raw.get("done", False)
        if not isinstance(done, bool):
            raise ChecklistFormatError(f"пункт {n}: done должно быть true или false")
        note = raw.get("note", "")
        if not isinstance(note, str):
            raise ChecklistFormatError(f"пункт {n}: note должно быть строкой")
        text = clean_text(raw["text"])
        if text:
            items.append(Item(text, done, clean_note(note)))
    return items


class Checklist:
    def __init__(self, items=()):
        self._items = list(items)
        self.path = None
        self.dirty = False

    @property
    def items(self):
        return tuple(self._items)

    def __len__(self):
        return len(self._items)

    @property
    def total(self):
        return len(self._items)

    @property
    def done_count(self):
        return sum(1 for it in self._items if it.done)

    @property
    def progress(self):
        return self.done_count / self.total if self._items else 0.0

    def _check_index(self, index):
        if type(index) is not int:
            raise TypeError("index must be an int")
        if not 0 <= index < len(self._items):
            raise IndexError(f"no item {index}")

    def add(self, text):
        text = clean_text(text)
        if not text:
            return None
        self._items.append(Item(text))
        self.dirty = True
        return len(self._items) - 1

    def set_done(self, index, done):
        self._check_index(index)
        item = self._items[index]
        if item.done != bool(done):
            self._items[index] = replace(item, done=bool(done))
            self.dirty = True

    def toggle(self, index):
        self._check_index(index)
        self.set_done(index, not self._items[index].done)

    def rename(self, index, text):
        self._check_index(index)
        text = clean_text(text)
        item = self._items[index]
        if not text or text == item.text:
            return False
        self._items[index] = replace(item, text=text)
        self.dirty = True
        return True

    def set_note(self, index, text):
        self._check_index(index)
        note = clean_note(text)
        item = self._items[index]
        if note == item.note:
            return False
        self._items[index] = replace(item, note=note)
        self.dirty = True
        return True

    def remove(self, index):
        self._check_index(index)
        self.dirty = True
        return self._items.pop(index)

    def move(self, src, dst):
        self._check_index(src)
        if type(dst) is not int:
            raise TypeError("index must be an int")
        dst = max(0, min(dst, len(self._items) - 1))
        if src != dst:
            self._items.insert(dst, self._items.pop(src))
            self.dirty = True
        return dst

    def to_dict(self):
        return {
            "version": FORMAT_VERSION,
            "items": [_item_dict(it) for it in self._items],
        }

    @classmethod
    def load(cls, path):
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except UnicodeDecodeError as e:
            raise ChecklistFormatError("файл не в кодировке UTF-8") from e
        except json.JSONDecodeError as e:
            raise ChecklistFormatError(f"ошибка JSON: {e}") from e
        checklist = cls(_parse(data))
        checklist.path = os.path.abspath(path)
        return checklist

    def save(self, path=None):
        target = path if path is not None else self.path
        if not target:
            raise ValueError("не указан файл для сохранения")
        target = os.path.abspath(target)
        write_json_atomic(target, self.to_dict())
        self.path = target
        self.dirty = False


def _item_dict(item):
    data = {"text": item.text, "done": item.done}
    if item.note:
        data["note"] = item.note  # absent key keeps note-less files unchanged
    return data


def write_json_atomic(target, data):
    # Temp file in the same folder so os.replace stays on one volume.
    fd, tmp = tempfile.mkstemp(prefix=".checkprog-", suffix=".tmp",
                               dir=os.path.dirname(target))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
