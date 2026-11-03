#!/usr/bin/env python3
# Блок B (Основной): разбор журналов в N процессах через os.fork, результат — через os.pipe.
# Автор: Шавкиев Аслан
#
# Использование:
#   logsplit.py [--logs ПАПКА] [-n N] [--quiet]
#
# Схема: родитель делит файлы между N детьми (по кругу), для каждого ребёнка создаёт
# пайп, форкается; ребёнок считает свою часть и пишет JSON в пайп, родитель читает
# все пайпы до EOF и обязательно делает waitpid() на каждого ребёнка (иначе зомби).
import argparse
import glob
import json
import os
import statistics
import subprocess
import sys
import time
from collections import defaultdict


def parse_file(path):
    """Автор: Шавкиев Аслан. Для одного файла: {путь: [всего, 5xx]}."""
    stats = defaultdict(lambda: [0, 0])
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 7:
                continue                      # битую строку пропускаем
            s = stats[parts[4]]
            s[0] += 1
            if parts[5][0] == "5":
                s[1] += 1
    return stats


def child_main(files, wfd):
    """Автор: Шавкиев Аслан. Работа ребёнка: разобрать свои файлы, отправить итог родителю через пайп."""
    result = {os.path.basename(f): parse_file(f) for f in files}
    data = json.dumps(result).encode()
    with os.fdopen(wfd, "wb") as w:           # закрытие конца записи = EOF для родителя
        w.write(data)


def run(files, n):
    """Автор: Шавкиев Аслан. Запускает n детей; возвращает объединённый словарь {файл: {путь: [всего, 5xx]}}."""
    chunks = [files[i::n] for i in range(n)]  # раздача по кругу
    children = []                              # [(pid, read_fd)]
    for chunk in chunks:
        rfd, wfd = os.pipe()
        pid = os.fork()
        if pid == 0:
            # ----- ребёнок -----
            try:
                os.close(rfd)
                for _, other_rfd in children:  # унаследованные концы чтения братьев не нужны
                    os.close(other_rfd)
                child_main(chunk, wfd)
                os._exit(0)
            except BaseException as e:         # никогда не возвращаться в код родителя
                print(f"child {os.getpid()} error: {e!r}", file=sys.stderr)
                os._exit(1)
        # ----- родитель -----
        os.close(wfd)                          # свой конец записи закрыть, иначе EOF не придёт
        children.append((pid, rfd))

    merged = {}
    for pid, rfd in children:
        with os.fdopen(rfd, "rb") as r:
            payload = r.read()                 # читаем до EOF
        _, status = os.waitpid(pid, 0)         # собираем ребёнка — никаких зомби
        if not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0):
            raise RuntimeError(f"ребёнок {pid} завершился неуспешно: статус {status}")
        merged.update(json.loads(payload))
    return merged


def report(merged):
    """Автор: Шавкиев Аслан. Печать доли 5xx по путям и по файлам, поиск сбоя."""
    by_path = defaultdict(lambda: [0, 0])
    by_file = defaultdict(lambda: [0, 0])
    for fname, paths in merged.items():
        for p, (tot, e5) in paths.items():
            by_path[p][0] += tot
            by_path[p][1] += e5
            by_file[fname][0] += tot
            by_file[fname][1] += e5

    print("\nДоля 5xx по путям:")
    print(f"{'путь':<18}{'запросов':>10}{'5xx':>7}{'доля':>9}")
    for p, (t, e) in sorted(by_path.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
        print(f"{p:<18}{t:>10}{e:>7}{100*e/t:>8.2f}%")

    print("\nДоля 5xx по файлам (топ-5 и медиана):")
    ranked = sorted(by_file.items(), key=lambda kv: -kv[1][1] / kv[1][0])
    for fname, (t, e) in ranked[:5]:
        print(f"{fname:<16}{t:>8}{e:>7}{100*e/t:>8.2f}%")
    shares = sorted(e / t for t, e in by_file.values())
    print(f"медиана по файлам: {100*shares[len(shares)//2]:.2f}%")

    # Сбой = пара (файл, путь) с максимальной долей 5xx
    best = max(
        ((fname, p, t, e) for fname, paths in merged.items() for p, (t, e) in paths.items()),
        key=lambda x: x[3] / x[2],
    )
    fname, p, t, e = best
    print(f"\nСБОЙ: путь {p} в файле {fname}: {e} из {t} запросов = {100*e/t:.1f}% ответов 5xx")
    return best


def show_children():
    """Автор: Шавкиев Аслан. Показывает ps для потомков текущего процесса и число зомби (должно быть 0)."""
    ps = subprocess.Popen(["ps", "-eo", "pid,ppid,stat,comm"], stdout=subprocess.PIPE, text=True)
    out = ps.communicate()[0].splitlines()
    me = str(os.getpid())
    mine = [l for l in out[1:] if l.split()[1] == me and int(l.split()[0]) != ps.pid]
    print("\nps: потомки родительского процесса (PID %s) после работы:" % me)
    print(out[0])
    for l in mine:
        print(l)
    zombies = [l for l in mine if "Z" in l.split()[2]]
    print(f"потомков: {len(mine)}, зомби: {len(zombies)}")


def bench(files, repeats=5):
    """Автор: Шавкиев Аслан. Время при N=1,2,4: прогрев + медиана из нескольких запусков."""
    run(files, 1)                              # прогрев кэша страниц
    print(f"Ядер CPU: {os.cpu_count()}; запусков на каждое N: {repeats}")
    print(f"{'N':>3}{'медиана, с':>12}{'мин, с':>9}{'ускорение':>11}")
    base = None
    for n in (1, 2, 4):
        ts = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            run(files, n)
            ts.append(time.perf_counter() - t0)
        med = statistics.median(ts)
        base = base or med
        print(f"{n:>3}{med:>12.3f}{min(ts):>9.3f}{base/med:>10.2f}x")


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--logs", default=os.path.join(here, "..", "project3", "logs"))
    ap.add_argument("-n", type=int, default=4, help="число рабочих процессов")
    ap.add_argument("--quiet", action="store_true", help="только время, без отчёта")
    ap.add_argument("--ps", action="store_true", help="показать ps после работы (проверка зомби)")
    ap.add_argument("--bench", action="store_true", help="замер времени при N=1,2,4")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.logs, "access_*.log")))
    if not files:
        sys.exit(f"нет файлов access_*.log в {args.logs}")

    if args.bench:
        bench(files)
        return

    t0 = time.perf_counter()
    merged = run(files, args.n)
    dt = time.perf_counter() - t0
    if not args.quiet:
        report(merged)
    print(f"\nN={args.n}: файлов={len(files)}, время={dt:.3f} с")
    if args.ps:
        show_children()


if __name__ == "__main__":
    main()
