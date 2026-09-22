# 🔄 Pentool CI/CD Integration Guide

Automate security scanning in your CI/CD pipeline.

---

## Quick Start

```bash
# One-line headless scan
pentool --url https://example.com --headless --output report.json

# Full pipeline
pentool --url https://example.com --headless \\
    --check xss,sqli,lfi,ssti \\
    --threads 20 --delay 0.2 \\
    --ai \\
    --crawl --depth 3 --max-pages 100 \\
    --format html --output results/report.html
```

## CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--url URL` | required | Target URL (can be repeated) |
| `--headless` | — | Run without TUI |
| `--output PATH` | — | Save report to file |
| `--check NAMES` | all | Comma-separated checks: `xss,sqli,lfi,ssti,xxe,ssrf,open_redirect,info_leak` |
| `--threads N` | 10 | Parallel scan threads |
| `--delay SEC` | 0.0 | Delay between requests |
| `--ai` | — | Enable AI-assisted scanning (endpoint discovery, WAF bypass, payload gen). Launches MCP server. |
| `--smart` | — | Launch TUI, proxy on, crawl target, detect tech (replaces `--real`). |
| `--crawl` | — | Crawl the target before scanning |
| `--crawl --js` | — | Crawl with JS rendering (Lightpanda) |
| `--crawl --ai` | — | Crawl + AI endpoint discovery |
| `--crawl --js --ai` | — | Full: crawl + JS + AI |
| `--crawl` | — | Crawl target before scanning |
| `--depth N` | 3 | Crawl depth |
| `--max-pages N` | 100 | Max crawl pages |
| `--format FMT` | auto | Report format: `json`, `html`, `csv`, `auto` |
| `--config PATH` | — | Custom config file |
| `--verbose` | — | Debug output |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Scan completed successfully |
| 1 | Scan failed (config error, network error, etc.) |
| 2 | Invalid arguments |

## GitHub Actions Integration

### Basic Scan

```yaml
name: Security Scan
on:
  schedule:
    - cron: '0 6 * * 1'  # Every Monday 6:00 UTC
  workflow_dispatch:      # Manual trigger

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install pentool
        run: uv tool install pentool

      - name: Run security scan
        run: |
          pentool --url https://example.com --headless \\
            --check xss,sqli,info_leak \\
            --format html --output scan-report.html

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: scan-report
          path: scan-report.html
```

### Full Pipeline with AI

```yaml
name: Full Security Audit
on:
  push:
    branches: [main, staging]
  workflow_dispatch:

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install pentool with AI
        run: |
          uv tool install pentool --with pentool-mcp-server
          pentool ai setup

      - name: Crawl and scan
        run: |
          pentool --url ${{ secrets.TARGET_URL }} --headless \\
            --threads 20 --delay 0.3 \\
            --ai \\
            --crawl --depth 5 --max-pages 200 \\
            --format json --output results.json

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: security-results
          path: results.json

      - name: Notify on findings
        if: failure()
        run: |
          echo "Security scan found issues!"
          # Add Slack/Discord/email notification here
```

### Docker-based Pipeline

```yaml
name: Docker Security Scan
on:
  workflow_dispatch:

jobs:
  docker-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t pentool .

      - name: Run scan in container
        run: |
          docker run --rm \\
            -v ${{ github.workspace }}/reports:/reports \\
            pentool --url https://example.com --headless \\
              --check xss,sqli \\
              --format html --output /reports/report.html

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: docker-scan-report
          path: reports/
```

## GitLab CI Integration

```yaml
stages:
  - security

security-scan:
  stage: security
  image: python:3.12-slim
  before_script:
    - pip install uv
    - uv tool install pentool
  script:
    - pentool --url https://example.com --headless
      --check xss,sqli
      --format html --output report.html
  artifacts:
    paths:
      - report.html
```

## Docker

### Build

```bash
docker build -t pentool .
```

### Run (headless)

```bash
docker run --rm pentool --url https://example.com --headless --output /tmp/report.json
```

### Run (TUI)

```bash
docker run -it --rm -p 8080:8080 pentool
```

### Docker Compose

```bash
docker compose up
```

## Tips

### Performance Tuning

- Start with `--threads 10` — increase if the target handles it
- Add `--delay 0.5` for rate-limited targets
- Use `--crawl` for dynamic sites (SPA, JS-heavy)
- Disable unneeded checks with `--check xss,sqli` for speed

### CI/CD Best Practices

1. **Schedule scans** — weekly is a good baseline
2. **Use `--format json`** — machine-readable for post-processing
3. **Archive reports** — track trends over time
4. **Notify on findings** — integrate with Slack/email
5. **Test in staging first** — before scanning production

### Troubleshooting

- **Scan hangs** — reduce `--threads`, add `--delay`
- **Too many false positives** — narrow `--check` list
- **Crawl finds nothing** — ensure Lightpanda binary is installed
- **AI not working** — run `pentool ai setup` first