#!/usr/bin/env bash
# scripts/run-tests.sh
#
# Единственная правильная точка запуска тестов. После успешного прогона пишет
# маркер .claude/state/tests-passed, который читает Stop-хук
# require-quality-gate.sh. Благодаря этому Stop-хук укладывается в ~10 секунд:
# он не перезапускает тесты, а проверяет, что маркер свежий (хеши файлов).
#
# Почему не запускать тесты прямо из Stop-хука: полный прогон занимает минуты,
# а блокирующий хук имеет жёсткий бюджет времени. См. README-starter-kit.md.
#
# Использование:
#   scripts/run-tests.sh              # TEST_CMD из окружения, иначе автоопределение
#   TEST_CMD="pytest -q" scripts/run-tests.sh
#   scripts/run-tests.sh -- pnpm test   # всё после -- передаётся как есть

set -uo pipefail

# .env читается, если есть (не наш секрет, а локальная конфигурация путей).
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env 2>/dev/null || true
  set +a
fi

# Конфигурация starter kit: TEST_COMMAND, WIN_HOST, WIN_TEST_SCRIPT.
# .env имеет приоритет (читается выше), config.env — значения по умолчанию.
if [ -f .claude/hooks/config.env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.claude/hooks/config.env 2>/dev/null || true
  set +a
  # В config.env переменная называется TEST_COMMAND; в .env — TEST_CMD.
  TEST_CMD="${TEST_CMD:-${TEST_COMMAND:-}}"
fi

cmd=""
if [ "${1:-}" = "--" ]; then
  shift
  cmd="$*"
elif [ -n "${TEST_CMD:-}" ]; then
  cmd="$TEST_CMD"
elif { [ -n "${WIN_HOST:-}" ] && [ -n "${WIN_TEST_SCRIPT:-}" ]; }; then
  cmd="ssh \"$WIN_HOST\" 'powershell.exe -ExecutionPolicy Bypass -File \"$WIN_TEST_SCRIPT\"'"
elif [ -f pyproject.toml ] || [ -f pytest.ini ] || [ -f tox.ini ]; then
  command -v pytest >/dev/null 2>&1 && cmd="pytest -q"
elif [ -f package.json ]; then
  command -v pnpm >/dev/null 2>&1 && cmd="pnpm test"
  [ -z "$cmd" ] && command -v npm >/dev/null 2>&1 && cmd="npm test --silent"
elif [ -f Cargo.toml ]; then
  cmd="cargo test --quiet"
elif [ -f go.mod ]; then
  cmd="go test ./..."
fi

if [ -z "$cmd" ]; then
  echo "run-tests: не удалось определить команду тестов." >&2
  echo "Задайте TEST_CMD в .env, например: TEST_CMD=\"pytest -q\"" >&2
  exit 1
fi

echo "run-tests: $cmd"
if ! bash -c "$cmd"; then
  echo "run-tests: тесты провалились, маркер НЕ обновлён." >&2
  exit 1
fi

# Маркер пишет сам хук — он единственный владелец формата.
if [ -x .claude/hooks/require-quality-gate.sh ]; then
  .claude/hooks/require-quality-gate.sh --record
else
  echo "run-tests: тесты прошли, но .claude/hooks/require-quality-gate.sh не найден — маркер не записан." >&2
fi
