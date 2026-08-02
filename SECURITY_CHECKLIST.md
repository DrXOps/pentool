# 🔐 Security & License Activation Checklist

## Цель
Проверить механизм активации/деактивации лицензий, защиту от манипуляций с ключами и утечки PRO-кода.

---

## 1. Активация лицензии

### 1.1 Успешная активация
- [ ] Запустить `pentool` (FREE версия)
- [ ] Перейти в Settings → License
- [ ] Ввести **валидный PRO ключ**
- [ ] Проверить: уведомление "License activated successfully"
- [ ] Проверить: в Settings отображается "Plan: PRO"
- [ ] Проверить: PRO-функции разблокированы (Turbo Intruder, Advanced Scanner)
- [ ] Перезапустить приложение → лицензия сохранена

### 1.2 Активация с невалидным ключом
- [ ] Ввести **несуществующий ключ** (random string)
- [ ] Проверить: ошибка "Invalid license key"
- [ ] Проверить: лицензия остаётся FREE
- [ ] Проверить: PRO-функции недоступны

### 1.3 Активация с истёкшим ключом
- [ ] Создать ключ с `expires_at` в прошлом через админку
- [ ] Ввести истёкший ключ
- [ ] Проверить: ошибка "License expired"
- [ ] Проверить: лицензия остаётся FREE

### 1.4 Активация с деактивированным ключом
- [ ] Деактивировать ключ через админку (`is_active = false`)
- [ ] Ввести деактивированный ключ
- [ ] Проверить: ошибка "License key is deactivated"
- [ ] Проверить: лицензия остаётся FREE

---

## 2. Деактивация лицензии

### 2.1 Деактивация через UI
- [ ] Активировать валидный PRO ключ
- [ ] Перейти в Settings → License → Deactivate
- [ ] Проверить: уведомление "License deactivated"
- [ ] Проверить: Plan изменён на FREE
- [ ] Проверить: PRO-функции заблокированы
- [ ] Перезапустить → лицензия FREE

### 2.2 Деактивация через админку
- [ ] Активировать валидный PRO ключ
- [ ] Деактивировать ключ через админку
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия автоматически сброшена на FREE
- [ ] Проверить: PRO-функции недоступны

---

## 3. Истечение срока действия

### 3.1 Истечение во время работы
- [ ] Создать ключ с `expires_at = now() + 5 минут`
- [ ] Активировать ключ
- [ ] Подождать 5+ минут
- [ ] Проверить: уведомление "License expired"
- [ ] Проверить: лицензия автоматически сброшена на FREE
- [ ] Проверить: PRO-функции заблокированы

### 3.2 Запуск с истёкшей лицензией
- [ ] Активировать временный ключ
- [ ] Дождаться истечения
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия FREE при старте
- [ ] Проверить: уведомление об истечении

---

## 4. Проверка целостности PRO-кода

### 4.1 Проверка подписи PRO-пакета
- [ ] Активировать PRO ключ (первый раз)
- [ ] Проверить: PRO-пакет скачан в `~/.pentool/pro/`
- [ ] Проверить: файл `signature.txt` присутствует
- [ ] Проверить лог: "PRO package signature verified"
- [ ] **Подменить** файл в `~/.pentool/pro/` (изменить `.py` файл)
- [ ] Перезапустить `pentool`
- [ ] Проверить: ошибка "PRO package signature mismatch"
- [ ] Проверить: PRO-функции недоступны (fallback на FREE)

### 4.2 Удаление PRO-пакета
- [ ] Активировать PRO ключ
- [ ] Удалить `~/.pentool/pro/` вручную
- [ ] Перезапустить `pentool`
- [ ] Проверить: PRO-пакет автоматически переустановлен
- [ ] Проверить: PRO-функции работают

### 4.3 Попытка использовать PRO без ключа
- [ ] Деактивировать лицензию (FREE)
- [ ] Проверить: PRO-пакет остаётся в `~/.pentool/pro/`
- [ ] Попытаться запустить Turbo Intruder
- [ ] Проверить: Turbo checkbox **disabled**
- [ ] Проверить: tooltip "requires PRO license"
- [ ] Проверить: даже если включить через код — блокировка

---

## 5. Манипуляции с ключами

### 5.1 Повторная активация одного ключа
- [ ] Активировать PRO ключ на машине A
- [ ] Активировать **тот же ключ** на машине B
- [ ] Проверить: ключ работает на обеих (или лимит device_id)
- [ ] Если есть лимит: проверить ошибку "Max activations reached"

### 5.2 Изменение `license.dat` вручную
- [ ] Активировать PRO ключ
- [ ] Найти `~/.pentool/license.dat`
- [ ] **Изменить** план на "enterprise" вручную
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия **переустановлена** с сервера
- [ ] Проверить: изменения отменены

### 5.3 Копирование `license.dat` на другую машину
- [ ] Активировать PRO ключ на машине A
- [ ] Скопировать `~/.pentool/license.dat` на машину B
- [ ] Запустить `pentool` на машине B
- [ ] Проверить: либо работает (если нет device_id), либо ошибка

### 5.4 Подделка лицензии (fake license.dat)
- [ ] Создать **поддельный** `license.dat` с plan="pro"
- [ ] Запустить `pentool`
- [ ] Проверить: лицензия **не принята** (signature/validation fail)
- [ ] Проверить: лицензия сброшена на FREE

---

## 6. Сетевые сценарии

### 6.1 Активация без интернета
- [ ] Отключить интернет
- [ ] Попытаться активировать ключ
- [ ] Проверить: ошибка "Network error" или "Cannot reach license server"
- [ ] Включить интернет → повторить активацию → успех

### 6.2 Проверка лицензии при запуске (offline)
- [ ] Активировать PRO ключ (online)
- [ ] Отключить интернет
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия работает из **кэша** (`license.dat`)
- [ ] Проверить: PRO-функции доступны

### 6.3 Grace period (если реализовано)
- [ ] Деактивировать ключ через админку
- [ ] Отключить интернет
- [ ] Запустить `pentool`
- [ ] Проверить: лицензия работает до 7 дней (grace period)
- [ ] После 7 дней → FREE

---

## 7. Backend проверки

### 7.1 Логи активации
- [ ] Активировать ключ
- [ ] Проверить в админке: запись в `activation_logs`
- [ ] Проверить: `device_id`, `ip_address`, `activated_at`

### 7.2 Лимит активаций
- [ ] Создать ключ с `max_activations = 1`
- [ ] Активировать на машине A
- [ ] Попытаться активировать на машине B
- [ ] Проверить: ошибка "Max activations reached"
- [ ] Деактивировать на A → активировать на B → успех

### 7.3 Деактивация через админку
- [ ] Активировать ключ
- [ ] В админке: Deactivate key
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия сброшена на FREE

---

## 8. Попытки обхода

### 8.1 Изменение системного времени
- [ ] Активировать временный ключ (expires в будущем)
- [ ] Изменить системное время **назад** (на год)
- [ ] Перезапустить `pentool`
- [ ] Проверить: лицензия валидна (или детект time tampering)

### 8.2 Reverse engineering PRO-кода
- [ ] Попытаться импортировать `pentool.pro` напрямую (без лицензии)
- [ ] Проверить: ImportError или "License required"
- [ ] Проверить: PRO-код **обфусцирован** (или PyArmor)

### 8.3 Monkey patching `has_feature()`
- [ ] Попытаться патчить `license_info.has_feature()` в runtime
- [ ] Проверить: либо блокировка, либо PRO всё равно недоступен

---

## 9. Миграция между планами

### 9.1 FREE → PRO
- [ ] Запустить как FREE
- [ ] Активировать PRO ключ
- [ ] Проверить: Turbo Intruder разблокирован
- [ ] Проверить: threads max 200 (был 5)
- [ ] Проверить: delay min 0 (был 100)

### 9.2 PRO → FREE
- [ ] Активировать PRO
- [ ] Деактивировать
- [ ] Проверить: Turbo Intruder **disabled**
- [ ] Проверить: threads max 5
- [ ] Проверить: delay min 100

### 9.3 PRO → Enterprise (если есть)
- [ ] Активировать Enterprise ключ
- [ ] Проверить: дополнительные функции доступны
- [ ] Проверить: в Settings "Plan: Enterprise"

---

## 10. Резюме

### Критические проверки:
- ✅ Валидация ключа через backend
- ✅ Проверка подписи PRO-пакета
- ✅ Автоматическая деактивация при истечении
- ✅ Блокировка PRO-функций без лицензии
- ✅ Защита от подделки `license.dat`
- ✅ Логирование активаций в backend

### Дополнительные меры:
- 🔒 Обфускация PRO-кода (PyArmor/Cython)
- 🔒 Device fingerprinting (лимит активаций)
- 🔒 Grace period для offline режима
- 🔒 Periodic license revalidation (каждые 24ч)

---

## Admin Login (Backend)

**URL:** `https://pentool-license.akashtanov2020.workers.dev/admin`

**Новый логин:**
- **Username:** `admin`
- **Password:** `Pentool_Admin_2026!Secure`

*(Старый пароль сброшен. Обнови в `.env` бэкенда)*

---

## База данных (Backend)

### Cloudflare D1 (Production)

1. **Войти в Cloudflare Dashboard:** https://dash.cloudflare.com
2. **Workers & Pages** → выбрать проект `pentool-license`
3. **Settings** → **Variables** → **D1 Database Bindings**
4. **Посмотреть таблицы:**
   ```bash
   wrangler d1 execute pentool-license-db --command "SELECT * FROM license_keys LIMIT 10"
   wrangler d1 execute pentool-license-db --command "SELECT * FROM activation_logs LIMIT 10"
   ```

### Локальная БД (Development)

1. **Клонировать репозиторий бэкенда:**
   ```bash
   cd /home/docx
   git clone https://github.com/docxqwerty/pentool-backend.git
   cd pentool-backend
   ```

2. **Установить wrangler:**
   ```bash
   npm install -g wrangler
   wrangler login
   ```

3. **Посмотреть локальную БД:**
   ```bash
   wrangler d1 execute pentool-license-db --local --command "SELECT * FROM license_keys"
   ```

4. **SQL запросы:**
   ```sql
   -- Все ключи
   SELECT * FROM license_keys;
   
   -- Активные PRO ключи
   SELECT * FROM license_keys WHERE plan = 'pro' AND is_active = 1;
   
   -- Логи активаций
   SELECT * FROM activation_logs ORDER BY activated_at DESC LIMIT 20;
   
   -- Ключи по email
   SELECT * FROM license_keys WHERE email = 'user@example.com';
   ```

---

## Дополнительные команды

### Создать тестовый ключ (через админку)
```bash
curl -X POST https://pentool-license.akashtanov2020.workers.dev/admin/keys \
  -H "Authorization: Basic YWRtaW46UGVudG9vbF9BZG1pbl8yMDI2IVNlY3VyZQ==" \
  -H "Content-Type: application/json" \
  -d '{
    "plan": "pro",
    "expires_at": "2027-12-31T23:59:59Z",
    "max_activations": 2,
    "email": "test@example.com"
  }'
```

### Деактивировать ключ
```bash
curl -X POST https://pentool-license.akashtanov2020.workers.dev/admin/keys/{key_id}/deactivate \
  -H "Authorization: Basic YWRtaW46UGVudG9vbF9BZG1pbl8yMDI2IVNlY3VyZQ=="
```

---

✅ **Чеклист готов для ручного тестирования**
