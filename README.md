# Draft Builder — Document Template Generator

Автоматическая генерация Word-шаблонов с Content Controls из юридических документов.

## Архитектура

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Source.docx    │────▶│ document_analyzer│────▶│  Source_config.json │
│  (с [●] и AI    │     │  + LLM + Domain  │     │  (структура + поля) │
│   комментами)   │     └──────────────────┘     └──────────┬──────────┘
└─────────────────┘                                         │
                                                            ▼
                                              ┌──────────────────────┐
                                              │  (ручная правка JSON │
                                              │   если нужно)        │
                                              └──────────┬───────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
┌─────────────────┐     ┌──────────────────┐  │  template_builder    │
│ Template.docx   │◀────│  Word с CC +     │◀─│                      │
│ (готовый шаблон)│     │  Custom XML Part │  └──────────────────────┘
└─────────────────┘     └──────────────────┘
```

## Файлы проекта

```
ContentControls_tools/
├── README.md
├── requirements.txt
├── xml_schema_and_cc_mapping_v2.md   # Документация по маппингу
│
├── src/                               # Исходники
│   ├── document_analyzer.py           # Парсер + LLM классификация
│   ├── template_builder.py            # Генератор .docx
│   ├── domain_config.py               # Загрузчик доменных конфигов
│   ├── llm_provider.py                # Абстракция LLM (Ollama/OpenRouter)
│   └── domains/                       # Доменные конфигурации
│       ├── _base_legal_ru.json        # Базовый юридический (РФ)
│       └── loan_agreement.json        # Договор займа
│
├── reference/                         # Справочные материалы
│   ├── build_template.py              # Ручной билдер (пример)
│   ├── CC_Inspector.bas               # VBA инспектор CC
│   └── CC_Inspector_ScriptLab.yaml    # Script Lab сниппет
│
├── examples/                          # Примеры ввода/вывода
│   ├── Dogovor_config.json
│   ├── Dogovor_Template.docx
│   └── Dogovor_Generated.docx
│
└── tests/                             # Тесты (pytest)
    └── ...
```

## Установка

```bash
pip install -r requirements.txt
```

### LLM (опционально)

По умолчанию используется Ollama с локальной моделью. Можно переключить на OpenRouter или другой провайдер через переменные окружения.

**Ollama:**
```bash
ollama serve
ollama pull qwen3:32b
```

**OpenRouter:**
```bash
set DRAFTBUILDER_LLM_PROVIDER=openrouter
set DRAFTBUILDER_LLM_API_KEY=sk-or-...
set DRAFTBUILDER_LLM_MODEL=qwen/qwen3-32b
```

## Переменные окружения

| Переменная | Значение по умолчанию | Описание |
|---|---|---|
| `DRAFTBUILDER_LLM_PROVIDER` | `ollama` | Провайдер LLM: `ollama` или `openrouter` |
| `DRAFTBUILDER_LLM_MODEL` | `qwen3:32b` | Имя модели |
| `DRAFTBUILDER_LLM_URL` | зависит от провайдера | URL API эндпоинта |
| `DRAFTBUILDER_LLM_API_KEY` | — | API ключ (для openrouter) |

**Ollama** — URL по умолчанию: `http://localhost:11434/api/generate`

**OpenRouter** — URL по умолчанию: `https://openrouter.ai/api/v1/chat/completions`

Чтобы сменить модель для Ollama:
```bash
set DRAFTBUILDER_LLM_MODEL=qwen2.5:14b
```

## Использование

### Полный цикл

```bash
# 1. Анализ документа (домен определяется автоматически)
python src/document_analyzer.py examples/Dogovor.docx

# С явным указанием домена
python src/document_analyzer.py examples/Dogovor.docx --domain loan_agreement

# Без LLM
python src/document_analyzer.py examples/Dogovor.docx --no-llm

# 2. (Опционально) Проверить/исправить JSON
code Dogovor_config.json

# 3. Сборка шаблона
python src/template_builder.py Dogovor_config.json output/Dogovor_Template.docx
```

### Список доменов

```bash
python src/document_analyzer.py --list-domains
```

## Домены

Доменная конфигурация определяет:
- **entity_hints** — regex-паттерны для определения сущностей (стороны договора, разделы)
- **type_hints** — regex-паттерны для определения типов полей (дата, сумма, адрес)
- **field_name_map** — маппинг русских слов → английские имена полей
- **optional_classifiers** — правила классификации optional-блоков
- **alternative_classifiers** — правила классификации альтернативных блоков
- **combo_options** — значения для выпадающих списков
- **llm_context** — промпты для LLM классификации

### Наследование

Домен может расширять базовый конфиг через поле `"extends"`:

```json
{
  "domain_id": "loan_agreement",
  "extends": "_base_legal_ru",
  "entity_hints": {
    "lender": { "pattern": "займодав|кредитор", "case_insensitive": true }
  }
}
```

Базовый конфиг `_base_legal_ru` содержит общую юридическую лексику (agreement, notice, dispute и т.д.). Доменный конфиг добавляет специфичные сущности и переопределяет правила.

### Создание нового домена

1. Скопировать `domains/loan_agreement.json` как шаблон
2. Изменить `domain_id`, `display_name`
3. Заполнить `entity_hints` — какие сущности есть в документе
4. Заполнить `type_hints` — какие типы полей специфичны для домена
5. Заполнить `field_name_map` — маппинг доменных терминов
6. Настроить `llm_context` — промпты с учётом специфики документа

## Формат JSON конфига

```json
{
  "meta": {
    "source_file": "input/Dogovor.docx",
    "domain": "loan_agreement",
    "namespace": "urn:draftbuilder:template:v1",
    "total_placeholders": 63
  },
  "paragraphs": [...],
  "placeholders": [
    {
      "id": 0,
      "para_idx": 2,
      "context": "ДАТА [●] ГОДА",
      "field_type": "date",
      "entity": "agreement",
      "field_name": "date",
      "xml_path": "agreement/date",
      "confidence": 0.85,
      "needs_review": false
    }
  ],
  "alternatives": [...],
  "optionals": [...],
  "xml_schema": {...},
  "combo_options": {...}
}
```

### Ручная правка JSON

Если LLM неправильно классифицировал поле:

```json
// Было (неправильно)
{
  "entity": "loan",
  "field_name": "date",
  "xml_path": "loan/date"
}

// Стало (исправлено)
{
  "entity": "agreement",
  "field_name": "city",
  "xml_path": "agreement/city"
}
```

После правки — перезапустить `template_builder.py`.

## Структура Content Controls

### Типы полей

| field_type | CC Type | Описание |
|------------|---------|----------|
| text | PlainText | Обычный текст |
| name | PlainText | Имя/наименование |
| date | Date | Дата с календарём |
| amount | PlainText | Сумма |
| days | ComboBox | Выбор срока |
| address | PlainText | Адрес |
| account | PlainText | Банковские реквизиты |
| dropdown | DropDown | Выбор из списка |

### Сущности

Сущности определяются доменным конфигом. Для `loan_agreement`:

| Entity | Описание |
|--------|----------|
| agreement | Реквизиты договора |
| lender | Займодавец |
| borrower | Заёмщик |
| loan | Параметры займа |
| interest | Проценты |
| provision | Предоставление |
| penalty | Неустойка |
| notice | Уведомления |
| covenants | Обязательства |
| representations | Заверения |
| default_events | Случаи неисполнения |
| dispute | Разрешение споров |

## Тестирование шаблона

### В Word (Windows/Mac)

1. Открыть сгенерированный .docx
2. Developer Tab → Design Mode — увидеть границы CC
3. Developer Tab → XML Mapping Pane — проверить Custom XML Part

### Script Lab (Office Add-in)

1. Установить Script Lab из AppSource
2. Импортировать `CC_Inspector_ScriptLab.yaml`
3. Запустить — покажет все CC и их binding

## Известные ограничения

1. **Транши** — repeating sections требуют ручной доработки
2. **Вложенные пути** — `lender/account/bank_name` может требовать правки XML схемы
3. **Форматирование** — базовые стили, не полное воспроизведение оригинала
4. **Альтернативы** — определяются по разделителю `/`, может быть неточно

## Troubleshooting

### LLM не отвечает

```bash
# Ollama — проверить сервер
curl http://localhost:11434/api/tags

# OpenRouter — проверить ключ
echo %DRAFTBUILDER_LLM_API_KEY%
```

### Word не открывает .docx

Скорее всего ошибка в OOXML. Распаковать и проверить:

```bash
# PowerShell
Expand-Archive Template.docx -DestinationPath template_unzipped
# Проверить XML вручную
```
