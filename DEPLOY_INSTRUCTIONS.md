# 🔧 Pentool Backend & Website — Инструкции по обновлению

## 📋 Резюме выполненной работы

### ✅ Что готово:
1. **Pentool v0.1.7** — опубликован на PyPI
2. **CHANGELOG.md** — создан с полной историей изменений
3. **README структура** — переводы перенесены в `docs/i18n/`
4. **Блок благодарностей** — добавлен во все языки (codeby.net)
5. **Блок донатов** — HTML готов в `website_donate_block.html`
6. **Security Checklist** — полный чеклист проверки лицензирования
7. **Память Claude** — сохранена информация о токенах и структуре

---

## 🌐 Обновление сайта pentool.pro

### Проблема:
Сайт не обновился автоматически после пуша.

### Решение:
Сайт pentool.pro, вероятно, размещён через:
- **Cloudflare Pages** (проверь в Cloudflare Dashboard)
- **Vercel/Netlify** (проверь в соответствующих панелях)
- **GitHub Pages** (проверь Settings → Pages в репозитории)

**Шаги:**
1. Найди где хостится pentool.pro:
   ```bash
   dig pentool.pro
   # Или проверь DNS в Cloudflare Dashboard
   ```

2. Если это Cloudflare Pages:
   - Зайди в Cloudflare Dashboard → Pages
   - Найди проект pentool.pro
   - Нажми "Retry deployment" для последнего коммита

3. Если это отдельный репозиторий:
   ```bash
   gh repo list docxqwerty | grep -i "pentool\|site\|web"
   ```
   - Найди репозиторий с сайтом
   - Обнови `website_donate_block.html` там

---

## 🔐 Обновление админ-пароля Backend

### Текущая ситуация:
- ADMIN_TOKEN хранится в GitHub Secrets (pentool-backend)
- Креды, которые я предложил, не работают (токен другой)

### Как обновить пароль:

#### Вариант 1: Через GitHub Secrets (рекомендуется)
```bash
cd /home/docx/pentool-backend

# Обнови secret через gh CLI:
gh secret set ADMIN_TOKEN --body "Pentool_Admin_2026!Secure"

# Или через веб-интерфейс:
# https://github.com/docxqwerty/pentool-backend/settings/secrets/actions
```

После обновления секрета, триггерни деплой:
```bash
git commit --allow-empty -m "chore: trigger redeploy"
git push origin main
```

#### Вариант 2: Через Wrangler напрямую
```bash
cd /home/docx/pentool-backend/worker

# Получи Cloudflare API token из GitHub Secrets:
gh secret list | grep CF_API_TOKEN

# Установи переменную окружения (временно):
export CLOUDFLARE_API_TOKEN="<значение из secrets>"

# Обнови secret в Cloudflare Worker:
wrangler secret put ADMIN_TOKEN
# Введи: Pentool_Admin_2026!Secure
```

---

## 🔍 Как получить текущий ADMIN_TOKEN

### Способ 1: Посмотреть в Cloudflare Dashboard
1. Зайди на https://dash.cloudflare.com
2. Workers & Pages → pentool-license
3. Settings → Variables → Edit variables
4. Найди `ADMIN_TOKEN` (значение скрыто, но можно пересоздать)

### Способ 2: Если есть доступ к старым логам деплоя
```bash
cd /home/docx/pentool-backend
gh run list --workflow "Deploy to Cloudflare Workers"
gh run view <run_id> --log
# Ищи строки с ADMIN_TOKEN (если не замаскированы)
```

### Способ 3: Просто пересоздай
Поскольку старый токен неизвестен, проще создать новый:
1. Сгенерируй сильный пароль:
   ```bash
   openssl rand -base64 32
   ```
2. Обнови через GitHub Secrets (Вариант 1 выше)
3. Задеплой backend
4. Используй новый пароль для входа в админку

---

## 🚀 Финальный деплой Backend

После обновления ADMIN_TOKEN:

```bash
cd /home/docx/pentool-backend

# Проверь что все файлы актуальны:
git status

# Если есть изменения — закоммить:
git add -A && git commit -m "chore: update admin credentials"

# Запуш (автоматически задеплоится через GitHub Actions):
git push origin main

# Или деплой вручную через wrangler:
cd worker
export CLOUDFLARE_API_TOKEN="<значение из secrets>"
wrangler deploy
```

---

## ✅ Проверка после деплоя

### 1. Проверь админку:
```bash
# Замени <NEW_TOKEN> на новый ADMIN_TOKEN:
curl -X GET https://pentool-license.akashtanov2020.workers.dev/api/admin/keys \
  -H "X-Admin-Token: <NEW_TOKEN>" | jq .
```

Должен вернуть список ключей:
```json
{
  "keys": [...],
  "total": 10
}
```

### 2. Проверь публичный API:
```bash
curl -X POST https://pentool-license.akashtanov2020.workers.dev/api/validate \
  -H "Content-Type: application/json" \
  -d '{"key": "PTOOL-TEST-1234-5678", "machine_id": "test-machine"}'
```

---

## 📝 Следующие шаги

1. **Найди где хостится pentool.pro** и обнови donate блок
2. **Обнови ADMIN_TOKEN** через GitHub Secrets
3. **Задеплой backend** (автоматически или через wrangler)
4. **Протестируй админку** с новым токеном
5. **Обнови криптокошельки** в `website_donate_block.html` на реальные

---

## 💾 Сохранено в память

- Все токены в GitHub Secrets (не в коде)
- README переводы в `docs/i18n/` (не в корне)
- ADMIN_TOKEN обновляется через `gh secret set` или Cloudflare Dashboard

---

**Если нужна помощь с конкретным шагом — дай знать!**
