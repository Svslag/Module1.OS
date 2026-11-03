#!/usr/bin/env bash
# Блок A (Базовый), задание 1.
# Автор: Шавкиев Аслан
#
# Для каждого файла журнала: число строк и число ответов 5xx.
# В конце: итог и файл с наибольшим числом 5xx.
# Использование: ./errors.sh [папка_с_логами]   (по умолчанию ../project3/logs)

set -u

# Автор: Шавкиев Аслан — путь к папке берём из аргумента, все переменные в кавычках
dir="${1:-"$(dirname "$0")/../project3/logs"}"

total_lines=0
total_5xx=0
max_5xx=-1
max_file=""

printf '%-16s %10s %8s\n' "file" "lines" "5xx"

for f in "$dir"/access_*.log; do
    [ -e "$f" ] || { echo "нет файлов в '$dir'" >&2; exit 1; }

    # wc -l < "$f": только число, без имени файла
    lines=$(wc -l < "$f")
    # поле 6 — код ответа; сравниваем как строку, чтобы не поймать 5xx в пути/длительности
    n5=$(awk '$6 ~ /^5[0-9][0-9]$/ { n++ } END { print n+0 }' "$f")

    printf '%-16s %10d %8d\n' "$(basename "$f")" "$lines" "$n5"

    total_lines=$((total_lines + lines))
    total_5xx=$((total_5xx + n5))
    if [ "$n5" -gt "$max_5xx" ]; then
        max_5xx=$n5
        max_file=$(basename "$f")
    fi
done

echo "----"
printf 'ИТОГО: строк=%d, 5xx=%d (%.3f%%)\n' \
    "$total_lines" "$total_5xx" "$(awk -v a="$total_5xx" -v b="$total_lines" 'BEGIN { print 100*a/b }')"
echo "Больше всего 5xx: $max_file ($max_5xx)"
