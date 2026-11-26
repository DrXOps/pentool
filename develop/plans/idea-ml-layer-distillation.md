# Идея: собственный ML-слой Pentool (классификатор + генератор payload'ов)

**Статус:** идея, не в плане. Записано 2026-11-25 по запросу владельца.
**Родитель:** [../PLAN.md](../PLAN.md) · **Бэклог:** [../backlog.md](../backlog.md)

Документ сохраняет замысел целиком (этапы 0–8, рецепты, бюджеты, риски), чтобы через
полгода не восстанавливать его по памяти. Это не обещание сделать — это спецификация
идеи с явными местами «сработает / гипотеза, нужен PoC».

---

## Сверка с текущим кодом (проверено 2026-11-25)

| Вопрос | Как есть сейчас |
|---|---|
| Что уже есть | Локальная модель **LFM2.5-350M-heretic**, GGUF ~350 МБ, CPU-only, через MCP-сервер (`services/ai/`), по умолчанию **выключена** (`ai_enabled=False`), PRO (`ai_analysis`, `ai_discovery`) |
| Задачи ИИ | Реестр `services/ai/prompts.py`: 10 задач (`xss_waf_bypass`, `choose_checks`, `crawl_endpoints`, `finding_analysis`, `generate_payloads`, `prioritize_params`, `discovery`, `discovery_subdomains`, `discovery_endpoints`, `discovery_params`, `discovery_param_fuzz`) |
| Зависимости | `torch`, `onnxruntime`, `transformers` в проекте **нет**; extra `ai` = `pentool-mcp-server` (+ `playwright`). Всё ML-железо идеи — новые зависимости (и новый вес установки) |
| Лицензии | Ядро — **AGPL-3.0**, PRO — **proprietary** (в ТЗ идеи было «предположительно MIT/Apache» — это не так). Учителя (DeepSeek, Claude) — только API, веса студентов (DistilBERT/TinyBERT/Qwen) — Apache-2.0/MIT, что совместимо; **но**: распространение весов вместе с proprietary PRO требует явного решения по условиям (см. «Открытые вопросы») |
| Hardware tier | Фактически уже есть «Minimal»: 350M на CPU. Идея добавляет GPU-тиры и второй путь (генерацию payload'ов) |
| Текущий бюджет ресурсов | Процесс AI — отдельный subprocess, останавливается вместе с приложением; «повесить ПК» сейчас не может по построению. Любая новая схема обязана это сохранить |

**Что идея меняет по сути:** сегодня ИИ — один маленький ассистент (payload'ы, WAF-bypass,
разбор находок). Идея делает ML-слой самостоятельной подсистемой с двумя путями
(быстрый классификатор ответов + медленный генератор payload'ов), обучением на
дистилляции от DeepSeek/Haiku и tier-деплоем под неизвестное железо пользователя.

---

## Роль и ограничения (из ТЗ)

ML-инженер полного цикла: дистилляция, multi-task энкодеры, QLoRA, ONNX/GGUF,
деплой на гетерогенном потребительском железе (CPU-only…12+ ГБ GPU), безопасная
деградация. Знает риски: distribution collapse, head interference, catastrophic
forgetting, calibration drift, VRAM/RAM exhaustion, «повешенный ПК».

**Продукт:** Pentool Pro — open-source пентест-сканер (лицензию уточнить — см. сверку
выше). ML-слой — помощник сканеру:

1. **Fast path** — классификатор помечает ответы «возможная уязвимость класса X».
2. **Slow path** — маленькая LLM генерирует мутации payload'ов для «интересных» параметров.

**Железо разработчика:** GTX 1660 Ti, 6 ГБ VRAM, fp16 (bf16/тензорных ядер нет).
**Железо пользователя:** неизвестно — от CPU-only ноутбука до сервера; **не должен
вешаться**. **Бюджет:** $100, цель ≤ $30. **Срок PoC:** ≤ 7 дней.

---

## Архитектура (фиксирована)

### Подсистема A — multi-task классификатор (fast path)

- **База:** `distilbert-base-multilingual-cased` (primary), `huawei-noah/TinyBERT_General_4L_312D`
  (fallback для слабого железа).
- **10 голов**, multi-label sigmoid: `is_xss`, `is_rce`, `is_ssrf`, `is_sqli`,
  `is_path_traversal`, `is_ssti`, `is_xxe`, `is_open_redirect`, `is_crlf_injection`,
  `is_context_legit` (анти-голова).
- **Вход:** пара `(request, response)` в едином текстовом формате.
- **Выход:** 10 скоров + опционально `evidence_span`.
- **Размер:** ≤ 300 МБ FP32, ≤ 80 МБ INT8, ≤ 15 МБ TinyBERT INT8.
- **Latency:** GPU ≤ 30 мс (batch=1), CPU ≤ 150 мс (batch=1) на среднем железе.

### Подсистема B — генератор payload'ов (slow path)

- **База:** `Qwen2.5-Coder-1.5B-Instruct` (primary), `Qwen2.5-Coder-0.5B-Instruct` (fallback).
- **Адаптеры:** 10 LoRA по классам **или** 1 multi-task LoRA — решить PoC на SQLi.
- **Размер:** база Q4 ≤ 1.2 ГБ, LoRA ≤ 20 МБ.
- **Latency:** GPU ≤ 500 мс на 10 payload'ов.

### Развёртывание — hardware-tiered (этап 6)

Классификатор — ONNX Runtime, один процесс, все головы в одном графе.
Генератор — llama.cpp / vLLM, опционально (на слабом железе может отсутствовать).
**Авто-детект железа и graceful degradation обязательны.**

---

## Этап 0. Спецификация и PoC-решения

1. **Контракт входа/выхода** обеих подсистем (JSON-схемы).
2. **`evidence_span`**: token head vs regex-постобработка.
3. **Адаптеры генератора**: 10 LoRA vs 1 multi-task — PoC на SQLi.
4. **Схема данных классификатора:** `input_text`, `hard_labels[10]`, `soft_labels[10]`,
   `rationale`, `difficulty`, `source`, `template_family`.
5. **Схема данных генератора:** `instruction`, `target_json`, `teacher_rationale`,
   `difficulty`, `style`, `vuln_class`.
6. **Таблица классов:** `{класс, нужен ли request, нужен ли response, нужен ли context,
   целевой объём, распределение источников}`.
7. **Черновик tier-таблицы** (полная — этап 6.2).

## Этап 1. Данные: гибридный учитель (DeepSeek + Haiku)

1. **Скрипт-генератор шаблонов** — промт для DeepSeek V3/V4, который пишет
   `generate_templates.py`: 10 классов + hard-negatives; обфускация (URL/unicode/hex/
   comments/case); 3 уровня сложности; дедуп по MinHash; pytest-тесты (парсинг payload'ов,
   покрытие `template_family`).
2. **Golden set (DeepSeek)** — сложные семантически богатые примеры с soft labels и
   rationales: context-dependent атаки (XSS внутри JS-фреймворка, SQLi в ORM-контексте,
   SSRF через cloud metadata), обфускация, WAF-bypass; few-shot не пересекается с
   шаблонами; **запрет на галлюцинации CVE**.
3. **Массовка (Haiku Batch API)** — простые/средние примеры + hard-negatives с soft
   labels; ≥ 20 % hard-negatives; разнообразие стилей.
4. **Распределение объёмов:** шаблоны ~30 % (покрытие, чистые метки), DeepSeek golden
   ~10–15 % (якорь качества), Haiku ~55–60 % (масштаб).
5. **Бюджет:** Haiku ~$5–10 (20–30k примеров), DeepSeek ~$5–15 (3–5k golden, V3) или
   ~$10–25 (V4 Pro), скрипт ~$0.50–2. **Итого ~$11–37** — в бюджете с запасом.
6. **Валидация ответов учителей:** schema-check, парсинг, дедуп, сверка с публичными
   корпусами.
7. **Ревью данных** агентом DeepSeek: выборочно 100–200 примеров, флаг «подозрительно»,
   перегенерация.
8. **Quality gate:** ≥ 95 % JSON-valid, ≥ 20 % hard-negatives, нет утечки train/val по
   `template_family`, ручная выборка 100 примеров ок.

## Этап 2. Дистилляция классификатора

1. **Loss:** `α · KL(softmax(teacher/T) || softmax(student/T)) + (1−α) · BCE(hard_labels, student)`,
   T = 2–4, α = 0.7.
2. **Рецепт:** AdamW, lr 2e-5 (голова) / 1e-5 (база), batch 16–32, epochs 5–10, early
   stopping по val KL, fp16. `[оценка: 40–90 мин на 20k]`.
3. **Защита от head interference:** мониторинг per-head F1, опционально PCGrad.
4. **Метрики:** per-head F1 ≥ 0.90 (цель 0.95), ECE ≤ 0.05, PR-AUC, confusion на
   hard-negatives.
5. **Quality gate:** все F1 ≥ 0.85, ECE ≤ 0.08, FP rate на hard-negatives ≤ 5 %.

## Этап 3. Экспорт и валидация классификатора

1. ONNX export (opset 17, dynamic axes).
2. **Три версии:** FP16 ~160 МБ (GPU), INT8 ~80 МБ (CPU/слабый GPU), TinyBERT INT8 ~15 МБ
   (минимальный tier).
3. **Валидация каждой:** деградация F1 ≤ 2 % (INT8) / ≤ 5 % (TinyBERT), latency на CPU
   (i5–i7) и GPU (1660 Ti), размер.
4. **Инференс:** один процесс ONNX Runtime, все головы в одном графе.
5. Latency-бюджеты — в tier-таблице.

## Этап 4. Дистилляция генератора

1. Учитель: DeepSeek (golden) + Haiku (массовка).
2. Формат: `instruction` (system+user) → `target_json` (assistant); rationale как CoT —
   только если улучшает JSON-validity на PoC.
3. Решение по адаптерам — из этапа 0.
4. **QLoRA:** r=16, alpha=32, lr=2e-4, 2–3 эпохи, seq_len=1024, batch=1 + grad_accum=8.
   `[оценка: 2–5 ч на адаптер]`; если > 24 ч суммарно — брать 0.5B или сокращать объём.
5. **Две версии:** 1.5B (GPU ≥ 4 ГБ), 0.5B (GPU 2–4 ГБ; на CPU генератор отключён).
6. **Quality gate:** JSON-validity ≥ 99 %, self-BLEU ≤ 0.6, KS-test по распределению,
   ручная выборка 50 payload'ов.

## Этап 5. Экспорт и валидация генератора

1. GGUF Q4_K_M для llama.cpp.
2. **Multi-LoRA:** vLLM `--enable-lora` (проверить Turing — может не работать);
   llama.cpp — переключение адаптеров через API; **fallback** — одна база +
   последовательная загрузка адаптеров.
3. Latency ≤ 500 мс на 10 payload'ов (GPU).
4. VRAM: база Q4 + 1 адаптер ≤ 1.5 ГБ (1.5B) / ≤ 0.6 ГБ (0.5B).

## Этап 6. Hardware-tiered деплой

### 6.1. Авто-детект (`detect_hardware.py` или функция в Go)

GPU (`nvidia-smi`, `torch.cuda.is_available`, NVML), VRAM (всего/свободно), RAM, CPU
(ядра, AVX2/AVX512 — критично для ONNX/llama.cpp), ОС и рантаймы (CUDA, ROCm, Metal,
CPU-only) → `hardware_profile.json` с рекомендацией tier.

### 6.2. Таблица tier'ов

| Tier | Критерий | Классификатор | Генератор | VRAM | RAM | Latency |
|---|---|---|---|---|---|---|
| **Minimal** | CPU-only, ≤ 8 ГБ RAM | TinyBERT INT8 (CPU) | **отключён** | 0 | ≤ 1.5 ГБ | ~150 мс/запрос `[оценка]` |
| **Low** | GPU 2–4 ГБ | DistilBERT INT8 | Qwen 0.5B Q4 | ≤ 1.5 ГБ | ≤ 2 ГБ | 30 мс / 800 мс `[оценка]` |
| **Medium** | GPU 4–6 ГБ | DistilBERT INT8 | Qwen 0.5B Q4 + 10 LoRA | ≤ 2 ГБ | ≤ 3 ГБ | 20 мс / 500 мс `[оценка]` |
| **High** | GPU 6–12 ГБ | DistilBERT FP16 | Qwen 1.5B Q4 + 10 LoRA | ≤ 3 ГБ | ≤ 4 ГБ | 15 мс / 400 мс `[оценка]` |
| **Ultra** | GPU ≥ 12 ГБ | DistilBERT FP16 | Qwen 1.5B Q5 | ≤ 4 ГБ | ≤ 6 ГБ | 10 мс / 300 мс `[оценка]` |

### 6.3. Graceful degradation

Порядок отключения при нехватке ресурсов:

```
генератор (slow path)
  └─> только топ-3 головы (XSS, SQLi, SSRF)
        └─> INT8 → TinyBERT INT8
              └─> классификатор остаётся всегда (это ядро фичи)
```

Защита от «повесить ПК»:
- hard cap VRAM: `min(free_vram × 0.7, tier_budget)`;
- hard cap RAM: `min(free_ram × 0.5, tier_budget)`;
- watchdog: latency > 5× бюджета 10 раз подряд → автоматический downgrade tier'а;
- circuit breaker: OOM/crash → откат на tier ниже + запись в лог.

Batching и throttling: классификатор — batch до 8, timeout 100 мс; генератор — batch=1,
timeout 2 с, max_concurrent=1; при нагрузке от сканера приоритет классификатору,
генератор в очереди.

Мониторинг: latency p50/p99, VRAM/RAM, tier, число отказов — Prometheus-совместимо.

### 6.4. Установка и «вес»

- **Модели не бандлятся в репозиторий**: `pentool-pro ml install --tier=<auto|minimal|low|medium|high|ultra>`.
- `--tier=auto` — авто-детект + рекомендация, но **с подтверждением** пользователя.
- Размер загрузки: Minimal ~15 МБ; Low–Medium ~100 МБ; High–Ultra ~1.5 ГБ.
- `--no-ml` — полное отключение ML-слоя.
- В README — таблица «что вы получите на своём железе».

### 6.5. Тестирование tier-деплоя

Эмуляция слабого железа (`CUDA_VISIBLE_DEVICES` + `nvidia-smi -pl`, cgroups для RAM,
`taskset` для CPU); матрица «каждый tier × 3 сценария (холостой, лёгкий скан, тяжёлый
скан)» → метрики; перед релизом — прогон на реальном слабом железе или эмуляция.

## Этап 7. Интеграция в Pentool Pro

1. API (JSON-RPC/REST): `/analyze`, `/generate`, `/tier`, `/health`.
2. Асинхронный batch для классификатора, sync single для генератора.
3. Кэш `hash(request, response)` → scores, TTL 1 ч.
4. Метрики: p50/p99, FP rate, доля `is_context_legit=true`, распределение tier'ов.
5. **Open-source артефакты:** model card (данные, метрики, ограничения, tier-таблица);
   скрипты воспроизведения обучения (seed, версии библиотек); лицензии (Apache 2.0);
   инструкция деплоя (docker-compose с профилями под tier'ы); `detect_hardware.py` +
   тесты; документация «что вы получите на своём железе».

## Этап 8. Бюджет, таймлайн, риски

**Расходы:** DeepSeek (скрипты + golden + ревью) ~$6–27; Haiku Batch ~$5–10; аренда GPU
$0; VPS ~$6–20/мес. Против бюджета $100 — запас есть.

**Таймлайн:** этап → длительность → блокеры → критерий «готово» (7 дней до PoC).

**Риски и mitigation (красный флаг в скобках):**

| Риск | Mitigation |
|---|---|
| distribution collapse | смесь источников (шаблоны/golden/массовка), контроль разнообразия (self-BLEU, KS), ранняя остановка |
| head interference | per-head F1 мониторинг, опcционально PCGrad, раздельные lr голов |
| catastrophic forgetting | малый lr базы, короткие эпохи, eval на «старых» классах |
| calibration drift после INT8 | ECE до/после, temperature scaling, откат на FP16-тир |
| multi-LoRA на Turing не работает | fallback: последовательная загрузка адаптеров |
| галлюцинации учителей (CVE и пр.) | запрет в промте, schema-check, сверка с корпусами, ручное ревью |
| лицензионные проблемы | только Apache-2.0/MIT веса, API-учителя, явное решение по PRO |
| OOM на слабом железе | hard caps, circuit breaker, downgrade tier'а |
| «повешенный ПК» из-за генератора | max_concurrent=1, timeout 2 с, приоритет классификатору, `--no-ml` |
| CUDA-драйвер старше требований | CPU-fallback, проверка версии в detect_hardware |
| нет AVX2 — INT8 ONNX падает | проверка AVX2, иначе FP32/TinyBERT или CPU-без-ONNX |

**Fallback-план:** классификатор не бьёт логику → experimental feature; генератор не даёт
прироста → отключить по умолчанию; дистилляция не сработала → обычный fine-tune;
пользователь на Minimal → только классификатор.

---

## Открытые вопросы к заказчику

1. **Лицензия Pentool Pro** — по коду ядро AGPL-3.0, PRO proprietary. Как распространять
   веса студентов: вместе с PRO, отдельным пакетом, или только скрипты обучения?
2. **Есть ли тестовый стенд** с разным железом (CPU-only, 4 ГБ GPU) или только эмуляция?
3. **Готовы ли к 24+ ч обучения генератора** (или строго ≤ 7 дней на всё, тогда 0.5B)?
4. **Приемлемо ли 0.5B** как единственная модель генератора на первом релизе?
5. **Нужен ли `evidence_span` в v1** или достаточно скоров?
6. **Какой минимальный tier обязателен к релизу** — Minimal (только классификатор) или
   Low (классификатор + генератор)?

## Проверки перед стартом (когда идея станет задачей)

- `[TBD: эксперимент]` реальная скорость Qwen 7B Q4 на 1660 Ti (≥ 15 ток/с) — иначе
  локальный учитель не используется.
- `[TBD: эксперимент]` проходят ли `ONNX Runtime` и `llama.cpp` на Turing с актуальным
  CUDA-драйвером в нашей упаковке.
- `[TBD: эксперимент]` RAM/VRAM пик минимального и низкого tier'ов (поставить до
  обещаний в документации).
