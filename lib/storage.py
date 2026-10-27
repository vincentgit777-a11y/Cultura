"""
TECHNOVANA — local JSON storage helpers.

The project deliberately avoids a database. All persistent data lives in plain
JSON files inside the `data/` folder, which sits **outside** the `static/`
folder so it can never be downloaded directly by a browser.

Two things matter for correctness here:

1. **Safe reads.** A malformed or unreadable file must produce a controlled
   error for the visitor — never a raw traceback.
2. **Safe writes.** A plain read-modify-write is not safe when two requests
   arrive at the same moment, so writes take an exclusive lock on a lock file
   and the new file is swapped in atomically with `os.replace()`.

This is a deliberate, simple strategy for a local prototype. It is not a
replacement for a real database on a busy deployment.
"""

import errno
import json
import os
import tempfile
import threading
from contextlib import contextmanager

try:  # Windows
    import msvcrt
except ImportError:  # POSIX
    msvcrt = None

try:  # POSIX
    import fcntl
except ImportError:
    fcntl = None


class StorageError(Exception):
    """Raised when a data file cannot be read or written safely."""


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _lock_path(path):
    return path + ".lock"


@contextmanager
def file_lock(path):
    """
    Acquire an exclusive lock for `path` for the duration of the block.

    A separate `.lock` file is used because the data file itself is replaced
    atomically, which would break a lock held on the original inode.
    """
    lock_file = _lock_path(path)
    directory = os.path.dirname(os.path.abspath(lock_file))
    if directory:
        os.makedirs(directory, exist_ok=True)

    with _LOCKS_GUARD:
        handle_lock = _LOCKS.setdefault(lock_file, threading.Lock())

    with handle_lock:
        handle = open(lock_file, "a+b")
        try:
            if msvcrt is not None:
                # Windows: lock a single byte at the start of the file.
                handle.seek(0)
                if handle.read(1) == b"":
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            elif fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if msvcrt is not None:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                elif fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError as exc:  # pragma: no cover - platform specific
                if exc.errno not in (errno.EACCES, errno.EBADF):
                    raise
            finally:
                handle.close()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def read_json(path, default=None):
    """
    Read and parse a JSON file.

    Returns `default` when the file does not exist. Raises `StorageError`
    when the file exists but cannot be read or is malformed.
    """
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise StorageError(
            "The data file '{}' contains invalid JSON (line {}, column {}).".format(
                os.path.basename(path), exc.lineno, exc.colno
            )
        )
    except OSError as exc:
        raise StorageError(
            "The data file '{}' could not be read ({}).".format(
                os.path.basename(path), exc.strerror or exc
            )
        )


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def write_json(path, payload):
    """
    Write `payload` to `path` atomically.

    The new content is written to a temporary file in the same directory and
    then moved into place, so a reader never sees a half-written file.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)

    handle = None
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".tmp-", suffix=".json", dir=directory or None
        )
        handle = os.fdopen(fd, "w", encoding="utf-8")
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
        os.replace(tmp_path, path)
        tmp_path = None
    except (OSError, TypeError, ValueError) as exc:
        raise StorageError(
            "The data file '{}' could not be saved ({}).".format(
                os.path.basename(path), exc
            )
        )
    finally:
        if handle is not None:
            handle.close()
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def update_json(path, default, mutator):
    """
    Read, transform and write back a JSON document under an exclusive lock.

    `mutator` receives the current document and must return the new one.
    This is the only supported way to modify a data file, because it closes
    the read-modify-write race between concurrent requests.
    """
    with file_lock(path):
        current = read_json(path, default)
        updated = mutator(current)
        write_json(path, updated)
        return updated
