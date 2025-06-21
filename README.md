# 📋 API для поиска правовых документов РФ

Комплексное решение для поиска и проверки статуса российских нормативных документов, включая ГОСТы, приказы, распоряжения и другие правовые акты.

## 🌟 Возможности

- **🔍 Поиск документов** по различным критериям
- **📊 Проверка статуса** документов (действующий, отменён, заменён, просрочен)
- **⚡ Асинхронный поиск** для повышения производительности
- **💾 Кеширование** результатов в Redis
- **📈 Мониторинг изменений** статуса документов

- **📝 Пакетная валидация** множества документов

## 🗂️ Поддерживаемые источники

| Источник | Описание | Типы документов |
|----------|----------|-----------------|
| [publication.pravo.gov.ru](http://publication.pravo.gov.ru/api) | Официальное опубликование правовых актов | Приказы, распоряжения, постановления |
| [you-right.ru](https://you-right.ru/api) | Юридические данные | Судебные документы, юридическая информация |
| [gostexpert.ru](https://gostexpert.ru) | База ГОСТов | ГОСТы, технические регламенты |
| [gostinfo.ru](https://www.gostinfo.ru) | Официальный источник стандартов | ГОСТы, технические регламенты |

## 🚀 Установка

```bash
# Клонирование репозитория
git clone https://github.com/your-repo/legal-documents-api.git
cd legal-documents-api

# Установка зависимостей
pip install -r requirements.txt

# Установка Redis (опционально, для кеширования)
# Ubuntu/Debian:
sudo apt-get install redis-server

# macOS:
brew install redis

# Windows:
# Скачайте Redis с официального сайта
```

## 📖 Быстрый старт

### Python API

```python
from legal_documents_api import LegalDocumentsAPI, DocumentType

# Создание экземпляра API
api = LegalDocumentsAPI()

# Поиск документов
documents = api.search_documents(
    query="коррозия",
    document_types=[DocumentType.GOST],
    limit=10
)

# Вывод результатов
for doc in documents:
    print(f"📄 {doc.title}")
    print(f"   Номер: {doc.number}")
    print(f"   Статус: {doc.status.value}")
    print(f"   URL: {doc.url}")
    print()

# Проверка статуса конкретного документа
status = api.check_document_status("gost_9014_78", DocumentType.GOST)
print(f"Статус документа: {status.value}")
```

### Асинхронный API

```python
import asyncio
from advanced_legal_api import AdvancedLegalAPI

async def main():
    api = AdvancedLegalAPI()
    
    # Асинхронный поиск
    documents = await api.search_documents_async(
        query="безопасность",
        limit=20
    )
    
    print(f"Найдено {len(documents)} документов")
    
    # Мониторинг изменений
    doc_ids = [doc.id for doc in documents[:5]]
    changes = api.monitor_document_changes(doc_ids)
    
    if changes:
        print("Обнаружены изменения:")
        for doc_id, new_status in changes.items():
            print(f"  {doc_id}: {new_status.value}")

# Запуск
asyncio.run(main())
```


## 🔧 Конфигурация

### Переменные окружения

```bash
# Redis для кеширования (опционально)
export REDIS_URL="redis://localhost:6379"

# Настройки API
export CACHE_TTL=3600  # Время жизни кеша в секундах
export REQUEST_TIMEOUT=30  # Таймаут запросов в секундах
```

### Конфигурационный файл

Создайте файл `config.json`:

```json
{
    "cache": {
        "redis_url": "redis://localhost:6379",
        "ttl": 3600
    },
    "api": {
        "timeout": 30,
        "retry_attempts": 3
    },
    "sources": {
        "pravo_gov": true,
        "gost_expert": true,
        "yurait": false
    }
}
```

## 📋 Типы документов

```python
from legal_documents_api import DocumentType

# Доступные типы
DocumentType.GOST           # ГОСТы
DocumentType.DECREE         # Приказы
DocumentType.ORDER          # Распоряжения
DocumentType.REGULATION     # Постановления
DocumentType.INSTRUCTION    # Инструкции
DocumentType.TECHNICAL_REGULATION  # Технические регламенты
DocumentType.LAW            # Законы
```

## 📊 Статусы документов

```python
from legal_documents_api import DocumentStatus

# Возможные статусы
DocumentStatus.VALID           # Действующий
DocumentStatus.INVALID         # Отменён
DocumentStatus.REPLACED        # Заменён
DocumentStatus.EXPIRED         # Просрочен
DocumentStatus.DRAFT           # Проект
DocumentStatus.PARTIALLY_VALID # Частично действует
DocumentStatus.UNKNOWN         # Неизвестно
```

## 🔍 Примеры использования

### Поиск ГОСТов

```python
# Поиск ГОСТов по теме
gosts = api.search_documents(
    query="сталь",
    document_types=[DocumentType.GOST],
    limit=20
)

# Фильтрация только действующих
valid_gosts = [doc for doc in gosts if doc.status == DocumentStatus.VALID]
```

### Поиск приказов и распоряжений

```python
from datetime import datetime, timedelta

# Поиск приказов за последний год
year_ago = datetime.now() - timedelta(days=365)
recent_decrees = api.search_documents(
    query="цифровизация",
    document_types=[DocumentType.DECREE, DocumentType.ORDER],
    date_from=year_ago
)
```

### Валидация документов проекта

```python
# Список документов из технического проекта
project_docs = [
    {'id': 'gost_123', 'type': DocumentType.GOST, 'context': 'Основной стандарт'},
    {'id': 'decree_456', 'type': DocumentType.DECREE, 'context': 'Нормативная база'},
    {'id': 'regulation_789', 'type': DocumentType.REGULATION, 'context': 'Требования безопасности'}
]

# Валидация
api = AdvancedLegalAPI()
results = api.batch_validate_documents(project_docs)

# Анализ результатов
for result in results:
    if not result['is_valid']:
        print(f"⚠️  Проблема с документом {result['document_id']}:")
        for issue in result['issues']:
            print(f"   - {issue}")
        for recommendation in result['recommendations']:
            print(f"   💡 {recommendation}")
```

### Мониторинг критических документов

```python
# Документы для мониторинга
critical_docs = ['gost_critical_1', 'decree_important_2']

# Настройка мониторинга
api = AdvancedLegalAPI()

while True:
    changes = api.monitor_document_changes(critical_docs)
    
    for doc_id, new_status in changes.items():
        if new_status in [DocumentStatus.INVALID, DocumentStatus.REPLACED]:
            print(f"🚨 КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: {doc_id} - {new_status.value}")
            # Отправка уведомления команде
            send_alert_to_team(doc_id, new_status)
    
    time.sleep(3600)  # Проверка каждый час
```

## 🛠️ Расширение функциональности

### Добавление нового источника данных

```python
class CustomLegalAPI(LegalDocumentsAPI):
    def __init__(self):
        super().__init__()
        self.base_urls['custom_source'] = 'https://api.custom-legal-source.com'
    
    def _search_custom_source(self, query: str) -> List[Document]:
        # Реализация поиска в вашем источнике
        url = f"{self.base_urls['custom_source']}/search"
        response = self.session.get(url, params={'q': query})
        
        documents = []
        for item in response.json():
            # Преобразование в объект Document
            doc = Document(
                id=item['id'],
                title=item['title'],
                # ... остальные поля
            )
            documents.append(doc)
        
        return documents
```

### Создание собственных уведомлений

```python
def send_telegram_notification(document_id: str, status: DocumentStatus):
    """Отправка уведомления в Telegram"""
    import requests
    
    bot_token = "YOUR_BOT_TOKEN"
    chat_id = "YOUR_CHAT_ID"
    
    message = f"📄 Изменение статуса документа {document_id}: {status.value}"
    
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={'chat_id': chat_id, 'text': message}
    )

# Использование в мониторинге
changes = api.monitor_document_changes(doc_ids)
for doc_id, new_status in changes.items():
    send_telegram_notification(doc_id, new_status)
```

## 🧪 Тестирование

```bash
# Запуск тестов
python -m pytest tests/

# Запуск с покрытием
python -m pytest tests/ --cov=legal_documents_api

# Интеграционные тесты
python -m pytest tests/integration/
```

## 📚 API Reference

### Класс LegalDocumentsAPI

#### `search_documents(query, document_types=None, date_from=None, date_to=None, limit=50)`

Поиск документов по запросу.

**Параметры:**
- `query` (str): Поисковый запрос
- `document_types` (List[DocumentType], optional): Типы документов для поиска
- `date_from` (datetime, optional): Дата начала периода
- `date_to` (datetime, optional): Дата окончания периода
- `limit` (int, optional): Максимальное количество результатов (по умолчанию 50)

**Возвращает:**
- `List[Document]`: Список найденных документов

#### `check_document_status(document_id, document_type)`

Проверка актуального статуса документа.

**Параметры:**
- `document_id` (str): Идентификатор документа
- `document_type` (DocumentType): Тип документа

**Возвращает:**
- `DocumentStatus`: Текущий статус документа

### Класс AdvancedLegalAPI

#### `search_documents_async(query, document_types=None, sources=None, limit=50)`

Асинхронный поиск документов.

#### `monitor_document_changes(document_ids)`

Мониторинг изменений статуса документов.

#### `batch_validate_documents(document_refs)`

Пакетная валидация документов.

## ⚠️ Ограничения

1. **Rate Limiting**: Некоторые API имеют ограничения на количество запросов
2. **Доступность источников**: Не все источники могут быть доступны 24/7
3. **Точность данных**: Статус документов может изменяться с задержкой
4. **Региональные ограничения**: Некоторые API могут быть недоступны вне России

## 🤝 Участие в разработке

1. Форкните репозиторий
2. Создайте ветку для новой функции (`git checkout -b feature/amazing-feature`)
3. Внесите изменения и добавьте тесты
4. Зафиксируйте изменения (`git commit -m 'Add amazing feature'`)
5. Отправьте изменения в ветку (`git push origin feature/amazing-feature`)
6. Создайте Pull Request

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл `LICENSE` для подробностей.

## 📞 Поддержка

- 📧 Email: support@legal-documents-api.com
- 💬 Telegram: [@legal_docs_support](https://t.me/legal_docs_support)
- 🐛 Issues: [GitHub Issues](https://github.com/your-repo/legal-documents-api/issues)

## 🙏 Благодарности

- [publication.pravo.gov.ru](http://publication.pravo.gov.ru) за предоставление API правовых актов
- [you-right.ru](https://you-right.ru) за юридические данные  
- [gostexpert.ru](https://gostexpert.ru) за базу ГОСТов
- Всем участникам проекта и сообществу разработчиков

---

**📌 Важно**: Этот API предназначен для информационных целей. Для официального использования всегда обращайтесь к первоисточникам и официальным публикациям документов. 