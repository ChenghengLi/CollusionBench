"""Minimal in-process virtual filesystem. Nothing here touches the host: paths are dictionary
keys, and model output is stored as text and never executed."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass


class VfsError(Exception):
    pass


@dataclass
class FileEntry:
    content: str
    author_wave: int | None  # last writer (agent index); None for files provided by the game
    area: str
    # Every agent that ever wrote this file. Overwriting never hides an earlier contributor.
    authors: frozenset[int] = frozenset()


class VirtualFS:
    READONLY = "/data"
    SHARED = "/workspace"
    SCRATCH = "/tmp"
    MAX_FILE_CHARS = 4000

    def __init__(self, strict_dirs: bool = False) -> None:
        self.files: dict[str, FileEntry] = {}
        # Files the game provides outside /data (folder descriptions): readable, never changed.
        self.locked: set[str] = set()
        # strict_dirs (card games): a folder exists once made or written into and stays after its
        # last file is deleted; listing any other path is an error. The default keeps the original
        # behaviour, where any path under an area lists as empty (DeepSeek blocked R, 2026-10-23:
        # "(empty)" for /workspace/orders read as an existing unit folder to file from).
        self.strict_dirs = strict_dirs
        self.dirs: set[str] = set()

    def add_dirs(self, path: str) -> None:
        if not self.strict_dirs:
            return
        area = self.area(path)
        while path not in ("/", area):
            self.dirs.add(path)
            path = posixpath.dirname(path)

    def put_locked(self, path: str, content: str) -> None:
        path = self.norm(path)
        self.files[path] = FileEntry(content, None, self.area(path))
        self.locked.add(path)

    def _check_unlocked(self, path: str) -> None:
        if path in self.locked:
            raise VfsError(f"{path}: read-only")

    @staticmethod
    def norm(path: str) -> str:
        p = posixpath.normpath("/" + str(path).strip().lstrip("/"))
        return "/" if p in ("/.", "//") else p

    def area(self, path: str) -> str:
        for root in (self.READONLY, self.SHARED, self.SCRATCH):
            if path == root or path.startswith(root + "/"):
                return root
        raise VfsError(f"{path}: no such directory")

    def put_readonly(self, path: str, content: str) -> None:
        self.files[self.norm(path)] = FileEntry(content, None, self.READONLY)

    def listdir(self, path: str) -> list[str]:
        path = self.norm(path)
        if path == "/":
            return [self.READONLY, self.SCRATCH, self.SHARED]
        self.area(path)
        if path in self.files:
            raise VfsError(f"{path}: not a directory")
        prefix = path.rstrip("/") + "/"
        children = {p[len(prefix) :].split("/")[0] for p in self.files if p.startswith(prefix)}
        children |= {d[len(prefix) :].split("/")[0] for d in self.dirs if d.startswith(prefix)}
        if self.strict_dirs and not children and path not in self.dirs \
                and path not in (self.READONLY, self.SHARED, self.SCRATCH):
            raise VfsError(f"{path}: no such folder")
        return sorted(children)

    def files_under(self, path: str) -> dict[str, FileEntry]:
        """Every file whose name a listing of `path` reveals (directly or via a subdirectory)."""
        prefix = self.norm(path).rstrip("/") + "/"
        return {p: e for p, e in self.files.items() if p.startswith(prefix)}

    def read(self, path: str) -> FileEntry:
        path = self.norm(path)
        if path not in self.files:
            raise VfsError(f"{path}: no such file")
        return self.files[path]

    def write(self, path: str, content: str, wave: int) -> FileEntry:
        path = self.norm(path)
        area = self.area(path)
        if area == self.READONLY:
            raise VfsError(f"{path}: read-only")
        self._check_unlocked(path)
        if path == area or any(p.startswith(path + "/") for p in self.files) or path in self.dirs:
            raise VfsError(f"{path}: is a directory")
        self._check_case(path)
        parent = posixpath.dirname(path)
        while parent not in ("/", area):
            if parent in self.files:
                raise VfsError(f"{parent}: not a directory")
            parent = posixpath.dirname(parent)
        previous = self.files.get(path)
        authors = (previous.authors if previous else frozenset()) | {wave}
        entry = FileEntry(str(content)[: self.MAX_FILE_CHARS], wave, area, authors)
        self.files[path] = entry
        self.add_dirs(posixpath.dirname(path))
        return entry

    def append(self, path: str, content: str, wave: int) -> FileEntry:
        """Add text to the end of a file (created if missing); every writer stays recorded."""
        path = self.norm(path)
        previous = self.files.get(path)
        joined = (previous.content + "\n" if previous and previous.content else "") + str(content)
        entry = self.write(path, joined, wave)
        return entry

    def delete(self, path: str) -> FileEntry:
        path = self.norm(path)
        if self.area(path) == self.READONLY:
            raise VfsError(f"{path}: read-only")
        self._check_unlocked(path)
        if path not in self.files:
            raise VfsError(f"{path}: no such file")
        return self.files.pop(path)

    def move(self, src: str, dst: str, wave: int) -> FileEntry:
        """Rename a file; the new name keeps the earlier writers and adds the mover."""
        src, dst = self.norm(src), self.norm(dst)
        entry = self.read(src)
        if entry.area == self.READONLY:
            raise VfsError(f"{src}: read-only")
        self._check_unlocked(src)
        moved = self.write(dst, entry.content, wave)
        moved.authors = moved.authors | entry.authors
        self.files.pop(src, None)
        return moved

    def mkdir(self, path: str) -> str:
        """Folders exist implicitly once a file is inside; this only checks the place is valid."""
        path = self.norm(path)
        if self.area(path) == self.READONLY:
            raise VfsError(f"{path}: read-only")
        if path in self.files:
            raise VfsError(f"{path}: a file with this name exists")
        if self.strict_dirs:
            parent = posixpath.dirname(path)
            while parent not in ("/", self.area(path)):
                if parent in self.files:
                    raise VfsError(f"{parent}: not a directory")
                parent = posixpath.dirname(parent)
            self._check_case(path)
        self.add_dirs(path)
        return path

    def _check_case(self, path: str) -> None:
        """strict_dirs: no second name that differs only in case from an existing file or folder
        (review 2026-10-23: /workspace/Logs/billing.csv passed for another unit's log)."""
        if not self.strict_dirs:
            return
        known: set[str] = set(self.dirs)
        for p in self.files:
            known.add(p)
            parent = posixpath.dirname(p)
            while parent != "/":
                known.add(parent)
                parent = posixpath.dirname(parent)
        lower = {k.lower(): k for k in known}
        prefix = ""
        for part in path.strip("/").split("/"):
            prefix += "/" + part
            k = lower.get(prefix.lower())
            if k is not None and k != prefix:
                raise VfsError(f"{path}: a name differing only in case exists ({k})")

    def wipe_scratch(self) -> None:
        self.files = {p: e for p, e in self.files.items() if e.area != self.SCRATCH}
