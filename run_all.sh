#!/usr/bin/env bash
# Проект 3 «Разбор журналов веб-сервера» — запуск всего одной командой:
#     bash run_all.sh
# Нужно: Ubuntu, python3 (3.11+), strace, procps (ps). Если чего-то нет:
#     sudo apt-get update && sudo apt-get install -y python3 strace procps
# Автор: Шавкиев Аслан
#
# Все результаты сохраняются текстом в output/.

set -u
cd "$(dirname "$0")" || exit 1
mkdir -p output

for tool in python3 strace ps awk; do
    command -v "$tool" > /dev/null || { echo "Нет '$tool'. Установите: sudo apt-get install -y python3 strace procps gawk" >&2; exit 1; }
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
    || { echo "Нужен Python 3.11+" >&2; exit 1; }

f="project3/logs/access_17.log"     # файл для задания A2 (любой, берём тот, где сбой)

echo "##### A1. errors.sh"
bash A_basic/errors.sh | tee output/A1_errors.txt

echo; echo "##### A2. strace -c: wc -l и свой Python-подсчёт на $f"
strace -c -S calls -o output/A2_strace_wc.txt     wc -l "$f"                        > /dev/null
strace -c -S calls -o output/A2_strace_python.txt python3 A_basic/count5xx.py "$f"  > /dev/null
for t in wc python; do
    echo "--- $t: три самых частых вызова"
    sed -n '1,5p' "output/A2_strace_$t.txt"
    echo "всего: $(tail -1 "output/A2_strace_$t.txt")"
done

echo; echo "##### B. os.fork + os.pipe (N=4), отчёт и ps"
python3 B_main/logsplit.py -n 4 --ps | tee output/B_logsplit.txt

echo; echo "##### B3. время при N=1, 2, 4"
python3 B_main/logsplit.py --bench | tee output/B_bench.txt

echo; echo "##### C1. три способа вернуть результат: время и strace -f -c"
bash C_advanced/compare_modes.sh 4 2>&1 | tee output/C1_compare.txt

echo; echo "##### C2. Ctrl+C во время работы"
bash C_advanced/demo_ctrlc.sh > output/C2_ctrlc.txt 2>&1
cat output/C2_ctrlc.txt

echo; echo "##### C3. начало и конец сбоя"
python3 C_advanced/find_failure.py | tee output/C3_failure.txt

echo; echo "Готово. Результаты в output/"
