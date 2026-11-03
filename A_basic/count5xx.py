#!/usr/bin/env python3
# Блок A (Базовый), задание 2: собственный Python-подсчёт для сравнения с `wc -l` под strace.
# Автор: Шавкиев Аслан
#
# Считает строки и ответы 5xx в одном файле. Использование: count5xx.py файл
import sys


def count(path):
    """Автор: Шавкиев Аслан. Возвращает (число строк, число 5xx) для одного файла журнала."""
    lines = 0
    n5 = 0
    with open(path) as f:           # текстовый режим: декодирование UTF-8 + буфер
        for line in f:
            lines += 1
            if line.split()[5][0] == "5":
                n5 += 1
    return lines, n5


if __name__ == "__main__":
    l, e = count(sys.argv[1])
    print(f"{sys.argv[1]}: lines={l} 5xx={e}")
