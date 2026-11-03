#!/usr/bin/env python3
# Блок C (Продвинутый), задание 3: начало и конец сбоя по времени в строках журнала.
# Автор: Шавкиев Аслан
#
# Метод: фоновые 5xx (~0.4%) разбросаны по всему журналу редкими одиночками. Сбой — плотный
# всплеск 5xx на одном пути. Берём 5xx каждого пути, сортируем по времени и склеиваем в
# кластеры, если разрыв между соседними 5xx <= GAP секунд. Сбой — кластер с наибольшим
# числом 5xx. Начало и конец — время его первой и последней строки.
#
# Использование: find_failure.py [папка_логов]
import glob
import os
import sys
from datetime import datetime
from collections import defaultdict

GAP = 300  # секунд; 5 минут


def ts(date, time_):
    """Автор: Шавкиев Аслан."""
    return datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M:%S")


def load_5xx(logs):
    """Автор: Шавкиев Аслан. {путь: [(время, файл, строка), ...]} только для 5xx."""
    ev = defaultdict(list)
    for fpath in sorted(glob.glob(os.path.join(logs, "access_*.log"))):
        with open(fpath) as f:
            for line in f:
                p = line.split()
                if len(p) == 7 and p[5][0] == "5":
                    ev[p[4]].append((ts(p[0], p[1]), os.path.basename(fpath), line.rstrip("\n")))
    return ev


def clusters(events):
    """Автор: Шавкиев Аслан. Разбить события, отсортированные по времени, на кластеры по разрыву > GAP."""
    events = sorted(events)
    out, cur = [], [events[0]]
    for e in events[1:]:
        if (e[0] - cur[-1][0]).total_seconds() <= GAP:
            cur.append(e)
        else:
            out.append(cur)
            cur = [e]
    out.append(cur)
    return out


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    logs = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "project3", "logs")
    ev = load_5xx(logs)

    best = None
    for path, events in ev.items():
        for c in clusters(events):
            if best is None or len(c) > len(best[1]):
                best = (path, c)
    path, c = best
    start, end = c[0], c[-1]
    dur = end[0] - start[0]
    files = sorted({x[1] for x in c})

    print(f"Путь сбоя: {path}")
    print(f"Файл(ы):   {', '.join(files)}")
    print(f"Начало:    {start[0]}   <- {start[2]}")
    print(f"Конец:     {end[0]}   <- {end[2]}")
    print(f"Длилось:   {dur} ({dur.total_seconds()/60:.0f} мин), 5xx в окне: {len(c)}")

    # Сколько запросов к этому пути было в окне и какова доля 5xx внутри окна
    tot = bad = 0
    for fpath in glob.glob(os.path.join(logs, "access_*.log")):
        with open(fpath) as f:
            for line in f:
                p = line.split()
                if len(p) == 7 and p[4] == path and start[0] <= ts(p[0], p[1]) <= end[0]:
                    tot += 1
                    bad += p[5][0] == "5"
    print(f"В окне к {path}: {tot} запросов, из них 5xx: {bad} ({100*bad/tot:.1f}%); "
          f"вне окна доля 5xx у этого пути ~0.5%")

    # Для сравнения: второй по величине кластер (фон) — чтобы видеть разницу масштаба
    others = sorted(
        ((len(x), p, x[0][0], x[-1][0]) for p, evs in ev.items() for x in clusters(evs)),
        reverse=True,
    )[1:3]
    print("Следующие кластеры (фон): " + "; ".join(f"{p}: {n} шт., {a}..{b}" for n, p, a, b in others))


if __name__ == "__main__":
    main()
