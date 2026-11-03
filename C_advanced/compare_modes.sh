#!/usr/bin/env bash
# Блок C (Продвинутый), задание 1: время и `strace -f -c` для трёх способов возврата результата.
# Автор: Шавкиев Аслан
#
# Использование: compare_modes.sh [N]   (по умолчанию N=4)

set -u
cd "$(dirname "$0")" || exit 1
n="${1:-4}"
out="../output"

echo "== Время (N=$n), 7 запусков на способ, медиана; без strace =="
printf '%-6s %10s %8s\n' mode "медиана,с" "мин,с"
for mode in pipe shm file; do
    python3 returns.py --mode "$mode" -n "$n" > /dev/null          # прогрев
    python3 - "$mode" "$n" <<'EOF'
import statistics, subprocess, sys, time
mode, n = sys.argv[1], sys.argv[2]
ts = []
for _ in range(7):
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "returns.py", "--mode", mode, "-n", n],
                   stdout=subprocess.DEVNULL, check=True)
    ts.append(time.perf_counter() - t0)
print(f"{mode:<6} {statistics.median(ts):>10.3f} {min(ts):>8.3f}")
EOF
done

echo
echo "== strace -f -c (все процессы: родитель + дети), сортировка по числу вызовов =="
for mode in pipe shm file; do
    strace -f -c -S calls -o "$out/C1_strace_$mode.txt" \
        python3 returns.py --mode "$mode" -n "$n" > /dev/null
    echo "--- $mode: топ-6 системных вызовов ---"
    head -8 "$out/C1_strace_$mode.txt"
    echo "всего: $(tail -1 "$out/C1_strace_$mode.txt")"
    echo
done
