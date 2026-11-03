#!/usr/bin/env bash
# Блок C (Продвинутый), задание 2: Ctrl+C во время работы.
# Автор: Шавкиев Аслан
#
# Для каждого из трёх способов: запускаем работу в своей группе процессов (как foreground-задание
# в терминале), через 1.5 с посылаем SIGINT всей группе (ровно то, что делает Ctrl+C) и проверяем:
# процессы завершились, зомби нет, в /dev/shm нет сегментов psm_*, временных каталогов logs_* нет.

set -u
cd "$(dirname "$0")" || exit 1

set -m   # job control: фоновая задача получает свою группу процессов (PGID = PID)

group_ps() {
    # Автор: Шавкиев Аслан — процессы заданной группы (портативно, без ps --pgid)
    ps -eo pid,ppid,pgid,stat,args | awk -v g="$1" 'NR==1 || $3==g' | cut -c1-90
}

left_over() {
    # Автор: Шавкиев Аслан — показать остатки ресурсов
    echo "  /dev/shm (psm_*): $(ls /dev/shm 2>/dev/null | grep -c '^psm_')"
    echo "  /tmp/logs_*:      $(ls -d /tmp/logs_* 2>/dev/null | wc -l)"
}

for mode in pipe shm file; do
    echo "=== способ: $mode ==="
    python3 returns.py --mode "$mode" -n 4 --repeat 40 &
    pgid=$!
    sleep 1.5

    echo "-- до Ctrl+C (процессы группы $pgid):"
    group_ps "$pgid"
    echo "-- во время работы:"
    left_over

    echo "-- посылаю SIGINT группе $pgid (аналог Ctrl+C)"
    kill -INT -- "-$pgid"
    wait "$pgid"
    echo "-- код завершения родителя: $? (130 = прервано по SIGINT)"
    sleep 0.5

    echo "-- после Ctrl+C: процессы группы $pgid:"
    group_ps "$pgid"
    echo "  процессов в группе (без заголовка): $(group_ps "$pgid" | tail -n +2 | wc -l)"
    echo "  зомби (STAT=Z) в группе:           $(group_ps "$pgid" | tail -n +2 | awk '$4 ~ /Z/' | wc -l)"
    echo "-- после Ctrl+C: остатки ресурсов:"
    left_over
    echo
done
