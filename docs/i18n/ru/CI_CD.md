# 🤖 CI/CD гайд — Pentool в автоматизации

Запуск Pentool **без TUI** (headless) для сканирования URL и генерации машинно-читаемого отчёта.

## Headless-команда

```bash
pentool --url https://example.com --headless --output result.json
```

- `--url` — цель(и); для нескольких повторите: `--url a --url b`.
- `--headless` — без TUI, без экрана, без взаимодействия.
- `--output` — путь отчёта: `.json`, `.html` или `.csv`.

Код выхода `0` — успех. `1` — сканер (PRO-функция) не установлен; в CI сделайте
`pentool license trial` (14-дневный бесплатный триал).

## GitHub Actions

```yaml
name: Pentool - security scan
on:
  push:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'
jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - name: Install Pentool
        run: uv tool install pentool
      - name: Headless scan
        run: pentool --url https://example.com --headless --output result.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: pentool-report
          path: result.json
```

## GitLab CI

```yaml
image: python:3.12-slim
stages: [scan]
scan:
  stage: scan
  script:
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.local/bin:$PATH"
    - uv tool install pentool
    - pentool --url https://example.com --headless --output result.json
  artifacts:
    paths: [result.json]
    expire_in: 2 weeks
```

## Jenkins (declarative)

```groovy
pipeline {
  agent any
  stages {
    stage('Pentool scan') {
      steps { sh '''
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
        uv tool install pentool
        pentool --url https://example.com --headless --output result.json
      ''' }
    }
  }
  post { success { archiveArtifacts artifacts: 'result.json' } }
}
```

## Cron / скрипт

```bash
0 6 * * *  pentool --url https://example.com --headless --output /var/reports/$(date +%F).json
```

## Чтение отчёта

`result.json` содержит находки: severity, name, url. Подходит для панелей/SIEM,
диффа между сборками (например, в GitHub Actions сравните с прошлым артефактом)
или прикрепления к трекерам инцидентов.

## Интерактивный режим (опционально)

`pentool --url https://example.com` (без `--headless`) запускает **TUI** и
предзаполняет Target этим URL — прокси стартует, проект готов к ручному аудиту.
Полная авто-запись в headless-браузер — в дорожной карте; для безлюдного запуска
используйте `--headless`.

## См. также

- [User Guide](USER_GUIDE.md)
- [Quick Start](QUICKSTART.md)
- [Pentool](https://github.com/DrXOps/pentool)
