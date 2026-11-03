#!/usr/bin/env python3
# Блок C (Продвинутый), задания 1 и 2.
# Автор: Шавкиев Аслан
#
# Три способа вернуть результат ребёнка родителю + корректная реакция на Ctrl+C:
#   --mode pipe  : os.pipe
#   --mode shm   : multiprocessing.shared_memory (сегмент в /dev/shm)
#   --mode file  : временные файлы
#
# Использование: returns.py --mode {pipe,shm,file} [-n N] [--repeat K]
#   --repeat K  — повторить разбор K раз (удлиняет работу, чтобы успеть нажать Ctrl+C)
#
# Ctrl+C: терминал шлёт SIGINT всей группе процессов. Дети сбрасывают SIGINT в SIG_DFL
# и умирают сразу; родитель ловит KeyboardInterrupt/SIGTERM, добивает оставшихся детей,
# собирает их waitpid() (нет зомби), закрывает и удаляет сегмент /dev/shm и временные файлы.
import argparse
import glob
import json
import os
import shutil
import signal
import struct
import sys
import tempfile
import time
from collections import defaultdict
from multiprocessing import shared_memory

SLOT = 256 * 1024          # размер слота разделяемой памяти на одного ребёнка
HDR = struct.Struct("<I")  # 4 байта: длина полезных данных


def parse_file(path):
    """Автор: Шавкиев Аслан. {путь: [всего, 5xx]} для одного файла."""
    stats = defaultdict(lambda: [0, 0])
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) != 7:
                continue
            s = stats[p[4]]
            s[0] += 1
            if p[5][0] == "5":
                s[1] += 1
    return stats


def work(files, repeat):
    """Автор: Шавкиев Аслан. Работа ребёнка (repeat раз, последний результат возвращается)."""
    result = {}
    for _ in range(repeat):
        result = {os.path.basename(f): parse_file(f) for f in files}
    return json.dumps(result).encode()


# ---------- ребёнок: отправка результата тремя способами ----------

def send_pipe(data, ctx, i):
    """Автор: Шавкиев Аслан. Способ 1: запись в пайп."""
    with os.fdopen(ctx["wfds"][i], "wb") as w:
        w.write(data)


def send_shm(data, ctx, i):
    """Автор: Шавкиев Аслан. Способ 2: запись в свой слот общей памяти (сегмент унаследован при fork)."""
    if len(data) + HDR.size > SLOT:
        raise ValueError("результат не помещается в слот")
    buf = ctx["shm"].buf
    off = i * SLOT
    buf[off + HDR.size: off + HDR.size + len(data)] = data
    HDR.pack_into(buf, off, len(data))   # длину пишем последней


def send_file(data, ctx, i):
    """Автор: Шавкиев Аслан. Способ 3: запись во временный файл (сначала .tmp, потом rename — атомарно)."""
    path = os.path.join(ctx["dir"], f"part{i}.json")
    with open(path + ".tmp", "wb") as w:
        w.write(data)
    os.rename(path + ".tmp", path)


# ---------- родитель: получение результата ----------

def recv_pipe(ctx, i):
    """Автор: Шавкиев Аслан."""
    with os.fdopen(ctx["rfds"][i], "rb") as r:
        return r.read()


def recv_shm(ctx, i):
    """Автор: Шавкиев Аслан."""
    buf = ctx["shm"].buf
    off = i * SLOT
    (n,) = HDR.unpack_from(buf, off)
    return bytes(buf[off + HDR.size: off + HDR.size + n])


def recv_file(ctx, i):
    """Автор: Шавкиев Аслан."""
    with open(os.path.join(ctx["dir"], f"part{i}.json"), "rb") as r:
        return r.read()


MODES = {"pipe": (send_pipe, recv_pipe), "shm": (send_shm, recv_shm), "file": (send_file, recv_file)}


class Interrupted(Exception):
    """Автор: Шавкиев Аслан. Поднимается обработчиком SIGINT/SIGTERM в родителе."""


def _on_signal(signum, frame):
    raise Interrupted(signal.Signals(signum).name)


def run(mode, files, n, repeat):
    """Автор: Шавкиев Аслан. Запуск n детей выбранным способом; возвращает объединённый результат."""
    send, recv = MODES[mode]
    chunks = [files[i::n] for i in range(n)]
    ctx = {}
    pids = []
    reaped = set()
    merged = {}
    shm = tmpdir = None
    try:
        # --- подготовка канала ---
        if mode == "shm":
            # track=False (Python 3.13+): не запускать служебный процесс resource_tracker —
            # сегмент мы удаляем сами в finally. На 3.11/3.12 параметра нет, работаем с трекером.
            try:
                shm = shared_memory.SharedMemory(create=True, size=SLOT * n, track=False)
            except TypeError:
                shm = shared_memory.SharedMemory(create=True, size=SLOT * n)
            ctx["shm"] = shm
        elif mode == "file":
            tmpdir = tempfile.mkdtemp(prefix="logs_")
            ctx["dir"] = tmpdir
        elif mode == "pipe":
            pairs = [os.pipe() for _ in range(n)]
            ctx["rfds"] = [r for r, _ in pairs]
            ctx["wfds"] = [w for _, w in pairs]

        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)

        # --- fork ---
        for i, chunk in enumerate(chunks):
            pid = os.fork()
            if pid == 0:
                # ----- ребёнок: никогда не возвращается в код родителя -----
                try:
                    signal.signal(signal.SIGINT, signal.SIG_DFL)   # Ctrl+C убивает сразу
                    signal.signal(signal.SIGTERM, signal.SIG_DFL)
                    if mode == "pipe":
                        for j in range(n):                          # чужие концы не нужны
                            os.close(ctx["rfds"][j])
                            if j != i:
                                os.close(ctx["wfds"][j])
                    send(work(chunk, repeat), ctx, i)
                    os._exit(0)
                except BaseException as e:
                    print(f"child {os.getpid()}: {e!r}", file=sys.stderr)
                    os._exit(1)
            pids.append(pid)
        if mode == "pipe":
            for w in ctx["wfds"]:
                os.close(w)                                         # родителю запись не нужна
            ctx["wfds"] = []

        # --- сбор ---
        for i, pid in enumerate(pids):
            payload = recv(ctx, i) if mode == "pipe" else None      # пайп: читаем до EOF
            _, st = os.waitpid(pid, 0)
            reaped.add(pid)
            if not (os.WIFEXITED(st) and os.WEXITSTATUS(st) == 0):
                raise RuntimeError(f"ребёнок {pid}: статус {st}")
            if payload is None:
                payload = recv(ctx, i)                              # shm/file: после завершения
            merged.update(json.loads(payload))
        return merged
    finally:
        # --- уборка выполняется всегда: и при успехе, и при Ctrl+C, и при ошибке ---
        signal.signal(signal.SIGINT, signal.SIG_IGN)               # не прерывать уборку повторным Ctrl+C
        # Каждый шаг уборки изолирован: сбой одного не должен пропускать остальные.
        # Гонка: Ctrl+C может прийти ровно в waitpid() — ребёнок уже собран, но в reaped
        # он ещё не записан; тогда повторный waitpid даёт ChildProcessError (это нормально).
        for pid in pids:
            if pid not in reaped:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, 0)                              # собрать — иначе зомби
                except ChildProcessError:
                    pass                                            # уже собран
        if mode == "pipe":
            for fd in ctx.get("rfds", []) + ctx.get("wfds", []):
                try:
                    os.close(fd)
                except OSError:
                    pass                                            # уже закрыт
        if shm is not None:
            try:
                shm.close()
            finally:
                try:
                    shm.unlink()                                    # убрать сегмент из /dev/shm
                except FileNotFoundError:
                    pass
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
        signal.signal(signal.SIGINT, signal.default_int_handler)


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--logs", default=os.path.join(here, "..", "project3", "logs"))
    ap.add_argument("--mode", choices=MODES, default="pipe")
    ap.add_argument("-n", type=int, default=4)
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.logs, "access_*.log")))
    t0 = time.perf_counter()
    try:
        merged = run(args.mode, files, args.n, args.repeat)
    except Interrupted as e:
        print(f"\nпрервано ({e}): дети завершены, ресурсы очищены", file=sys.stderr)
        sys.exit(130)
    dt = time.perf_counter() - t0
    total = sum(t for paths in merged.values() for t, _ in paths.values())
    e5 = sum(e for paths in merged.values() for _, e in paths.values())
    print(f"mode={args.mode} N={args.n} repeat={args.repeat}: строк={total} 5xx={e5} время={dt:.3f} с")


if __name__ == "__main__":
    main()
