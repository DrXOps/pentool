# 🤖 CI/CD Guide — Pentool in automation

Run Pentool **without the TUI** to scan a URL and emit a machine-readable report.

## Headless command

```bash
pentool --url https://example.com --headless --output result.json
```

- `--url` — target(s); repeat for multiple: `--url a --url b`.
- `--headless` — no TUI, no display, no interaction.
- `--output` — report path: `.json`, `.html`, or `.csv`. Omit to print findings only.

On success exits with status `0`; a `1` means the scanner (PRO feature) is not
installed — run `pentool license trial` for a 14-day free trial in CI.

## GitHub Actions

```yaml
name: Pentool - security scan

on:
  push:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'   # weekly, Mondays 06:00

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
        run: |
          pentool --url https://example.com --headless --output result.json
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
    paths:
      - result.json
    expire_in: 2 weeks
```

## Jenkins (declarative pipeline)

```groovy
pipeline {
  agent any
  stages {
    stage('Pentool scan') {
      steps {
        sh '''
          curl -LsSf https://astral.sh/uv/install.sh | sh
          export PATH="$HOME/.local/bin:$PATH"
          uv tool install pentool
          pentool --url https://example.com --headless --output result.json
        '''
      }
    }
  }
  post {
    success { archiveArtifacts artifacts: 'result.json' }
  }
}
```

## Cron / plain script

```bash
# daily at 06:00
0 6 * * *  pentool --url https://example.com --headless --output /var/reports/$(date +%F).json
```

## Reading the report

`result.json` lists findings with severity, name, and URL. Feed it into your
dashboard/SIEM, diff it across builds (e.g. in a GitHub Actions job compare
`result.json` against the previous artifact), or attach it to issue trackers.

## Interactive mode (optional)

`pentool --url https://example.com` (no `--headless`) launches the **TUI** and
pre-seeds the Target with that URL — the proxy starts and the project is ready
to audit by hand. Full auto-capture into a headless browser is on the roadmap;
for unattended runs prefer `--headless`.

## See also

- [User Guide](USER_GUIDE.md)
- [Quick Start](QUICKSTART.md)
- [Pentool](https://github.com/DrXOps/pentool)
