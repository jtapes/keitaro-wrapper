# Keitaro wrapper

Обёртка над Keitaro Admin API: веб-интерфейс для двух задач.

1. **Создаватор кампаний.** Название, гео-код страны и ID оффера -> кампания с двумя потоками:
   - поток 1: все посетители из выбранной страны (фильтр `country`, accept) уходят на `https://google.com`;
   - поток 2: выбранный оффер (100%).
   Домен, группа и источник выбираются из справочников Keitaro (значения по умолчанию - в `.env`).
2. **Редактор кампании.** Выбор кампании (поиск по названию или ID), просмотр потоков, офферов и статистики
   (клики, уникальные, конверсии, доход, расход, профит - за всё время, из `report/build`),
   добавление и удаление офферов. После каждого изменения доли офферов в потоке пересчитываются поровну,
   сумма всегда ровно 100% (3 оффера -> 34/33/33).

Стек: FastAPI, SQLAlchemy 2, Alembic, SQLite (по умолчанию), httpx, фронт - один HTML-файл на чистом JS без сборки.

## Запуск

Нужен Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # впишите KEITARO_API_KEY (Профиль -> API ключи в админке Keitaro)

alembic upgrade head          # миграции (создаёт таблицу campaign_log в SQLite)
uvicorn app.main:app --port 8000
```

Откройте http://localhost:8000.

### Настройки (`.env`)

| Переменная | Что |
|---|---|
| `KEITARO_URL` | адрес Keitaro, например `https://tlgk.host` |
| `KEITARO_API_KEY` | ключ Admin API |
| `DEFAULT_DOMAIN_ID`, `DEFAULT_GROUP_ID`, `DEFAULT_TRAFFIC_SOURCE_ID` | значения по умолчанию в форме создания |
| `CAMPAIGN_PREFIX` | префикс, который добавляется к названию, если его нет (`test_gorbachev_`) |
| `DATABASE_URL` | по умолчанию `sqlite:///./wrapper.db` |

Ключ и пароли в репозиторий не коммитятся (`.env` в `.gitignore`).

## Миграции

```bash
alembic upgrade head      # применить
alembic downgrade base    # откатить
alembic revision -m "..." --autogenerate   # новая миграция после правки app/models.py
```

База хранит журнал действий (`campaign_log`: что создано, какие офферы добавлены и удалены, когда),
он показывается в `GET /api/history`. Данные кампаний живут в Keitaro, копий в базе нет.

## API

| Метод | Путь | Что |
|---|---|---|
| GET | `/api/meta` | домены, группы, источники, офферы, значения по умолчанию |
| GET | `/api/campaigns?q=` | список кампаний (поиск по названию или ID) |
| POST | `/api/campaigns` | `{name, geo, offer_id, domain_id?, group_id?, traffic_source_id?}` |
| GET | `/api/campaigns/{id}` | кампания, потоки, офферы, статистика |
| POST | `/api/campaigns/{id}/streams/{stream_id}/offers` | `{offer_id}` - добавить оффер |
| DELETE | `/api/campaigns/{id}/streams/{stream_id}/offers/{offer_id}` | убрать оффер |
| GET | `/api/history` | журнал действий |

Swagger: http://localhost:8000/docs.

## Решения

- Если второй поток не создался, кампания удаляется - полусобранных кампаний в Keitaro не остаётся.
- Дубль оффера в потоке, оффер которого нет в потоке, поток-редирект вместо потока офферов -> понятная ошибка 422.
- Оффер не проверяется на существование: Keitaro принимает любой ID, а у тестового аккаунта часть офферов
  недоступна (403). Название неизвестного оффера показывается как «недоступен».
- Бизнес-логика (`app/service.py`) не зависит от FastAPI и покрыта тестами на эмуляции Keitaro.

## Тесты

```bash
pytest
```

`tests/live_check.py` - ручная проверка редактора на живом Keitaro (нужен запущенный сервер и своя тестовая кампания).

## Как работал с ИИ

Код писался вместе с ИИ-агентом: он разобрал API Keitaro на реальных запросах, набросал структуру и тесты;
поведение каждого эндпоинта проверено руками на живом Keitaro (кампании `test_gorbachev_*`).
