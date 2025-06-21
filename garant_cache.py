#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SQLite кеш для результатов поиска в системе ГАРАНТ
Сохраняет результаты поиска для избежания повторных запросов к системе ГАРАНТ
"""

import sqlite3
import json
import hashlib
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class GarantCache:
    """Класс для работы с SQLite кешем результатов ГАРАНТ"""

    def __init__(self, db_path: str = "garant_cache.db", cache_ttl_hours: int = 24 * 7):
        """
        Инициализация кеша

        Args:
            db_path: Путь к файлу базы данных SQLite
            cache_ttl_hours: Время жизни кеша в часах (по умолчанию 7 дней)
        """
        self.db_path = db_path
        self.cache_ttl_hours = cache_ttl_hours
        self._init_database()

    def _init_database(self):
        """Инициализация структуры базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Таблица для кеширования результатов поиска
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS garant_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query_hash TEXT UNIQUE NOT NULL,
                        original_query TEXT NOT NULL,
                        search_result TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        access_count INTEGER DEFAULT 1
                    )
                ''')

                # Индексы для улучшения производительности
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_query_hash ON garant_cache(query_hash)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON garant_cache(created_at)')

                conn.commit()
                logger.info(f"База данных кеша ГАРАНТ инициализирована: {self.db_path}")

        except Exception as e:
            logger.error(f"Ошибка при инициализации базы данных: {e}")
            raise

    def _get_query_hash(self, query: str) -> str:
        """
        Создание хеша для запроса

        Args:
            query: Поисковый запрос

        Returns:
            MD5 хеш запроса
        """
        # Нормализуем запрос для создания стабильного хеша
        normalized_query = query.strip().lower()
        return hashlib.md5(normalized_query.encode('utf-8')).hexdigest()

    def get_cached_result(self, query: str) -> Optional[Dict]:
        """
        Получение результата из кеша

        Args:
            query: Поисковый запрос

        Returns:
            Кешированный результат или None если не найден/устарел
        """
        query_hash = self._get_query_hash(query)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Получаем результат из кеша
                cursor.execute('''
                    SELECT search_result, created_at, access_count 
                    FROM garant_cache 
                    WHERE query_hash = ?
                ''', (query_hash,))

                row = cursor.fetchone()
                if not row:
                    return None

                search_result_json, created_at_str, access_count = row

                # Проверяем не устарел ли кеш
                created_at = datetime.fromisoformat(
                    created_at_str.replace('Z', '+00:00') if 'Z' in created_at_str else created_at_str)

                # Убираем timezone info для сравнения
                if created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=None)

                expiry_time = created_at + timedelta(hours=self.cache_ttl_hours)

                if datetime.now() > expiry_time:
                    # Кеш устарел, удаляем запись
                    cursor.execute('DELETE FROM garant_cache WHERE query_hash = ?', (query_hash,))
                    conn.commit()
                    logger.info(f"Удален устаревший кеш для запроса: {query[:50]}...")
                    return None

                # Обновляем статистику доступа
                cursor.execute('''
                    UPDATE garant_cache 
                    SET accessed_at = CURRENT_TIMESTAMP, access_count = access_count + 1 
                    WHERE query_hash = ?
                ''', (query_hash,))
                conn.commit()

                # Парсим результат из JSON
                result = json.loads(search_result_json)
                logger.info(
                    f"Найден кешированный результат для запроса: {query[:50]}... (использований: {access_count + 1})")
                return result

        except Exception as e:
            logger.error(f"Ошибка при получении из кеша: {e}")
            return None

    def save_result(self, query: str, result: Dict):
        """
        Сохранение результата в кеш

        Args:
            query: Поисковый запрос
            result: Результат поиска для сохранения
        """
        query_hash = self._get_query_hash(query)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Сериализуем результат в JSON
                result_json = json.dumps(result, ensure_ascii=False, indent=2)

                # Используем REPLACE для обновления существующих записей
                cursor.execute('''
                    INSERT OR REPLACE INTO garant_cache 
                    (query_hash, original_query, search_result, created_at, accessed_at, access_count)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                ''', (query_hash, query, result_json))

                conn.commit()
                logger.info(f"Сохранен результат в кеш для запроса: {query[:50]}...")

        except Exception as e:
            logger.error(f"Ошибка при сохранении в кеш: {e}")

    def clean_expired_cache(self):
        """Очистка устаревших записей из кеша"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Удаляем записи старше чем cache_ttl_hours
                expiry_timestamp = datetime.now() - timedelta(hours=self.cache_ttl_hours)

                cursor.execute('''
                    DELETE FROM garant_cache 
                    WHERE created_at < ?
                ''', (expiry_timestamp.isoformat(),))

                deleted_count = cursor.rowcount
                conn.commit()

                if deleted_count > 0:
                    logger.info(f"Удалено {deleted_count} устаревших записей из кеша")

        except Exception as e:
            logger.error(f"Ошибка при очистке кеша: {e}")

    def get_cache_stats(self) -> Dict:
        """
        Получение статистики кеша

        Returns:
            Словарь со статистикой кеша
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Общее количество записей
                cursor.execute('SELECT COUNT(*) FROM garant_cache')
                total_records = cursor.fetchone()[0]

                # Размер базы данных
                db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0

                # Самые популярные запросы
                cursor.execute('''
                    SELECT original_query, access_count, created_at 
                    FROM garant_cache 
                    ORDER BY access_count DESC 
                    LIMIT 5
                ''')
                popular_queries = cursor.fetchall()

                # Записи за последние 24 часа
                yesterday = datetime.now() - timedelta(hours=24)
                cursor.execute('''
                    SELECT COUNT(*) FROM garant_cache 
                    WHERE created_at > ?
                ''', (yesterday.isoformat(),))
                recent_records = cursor.fetchone()[0]

                return {
                    "total_records": total_records,
                    "db_size_bytes": db_size,
                    "db_size_mb": round(db_size / (1024 * 1024), 2),
                    "recent_records_24h": recent_records,
                    "popular_queries": [
                        {
                            "query": query[:100] + "..." if len(query) > 100 else query,
                            "access_count": count,
                            "created_at": created_at
                        }
                        for query, count, created_at in popular_queries
                    ],
                    "cache_ttl_hours": self.cache_ttl_hours
                }

        except Exception as e:
            logger.error(f"Ошибка при получении статистики кеша: {e}")
            return {}

    def clear_all_cache(self):
        """Полная очистка кеша"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM garant_cache')
                conn.commit()
                logger.info("Кеш полностью очищен")

        except Exception as e:
            logger.error(f"Ошибка при очистке кеша: {e}")

    def export_cache_to_json(self, output_path: str) -> bool:
        """
        Экспорт кеша в JSON файл

        Args:
            output_path: Путь для сохранения JSON файла

        Returns:
            True если экспорт успешен, False иначе
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT original_query, search_result, created_at, accessed_at, access_count
                    FROM garant_cache
                    ORDER BY created_at DESC
                ''')

                rows = cursor.fetchall()

                export_data = []
                for row in rows:
                    query, result_json, created_at, accessed_at, access_count = row
                    export_data.append({
                        "query": query,
                        "result": json.loads(result_json),
                        "created_at": created_at,
                        "accessed_at": accessed_at,
                        "access_count": access_count
                    })

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)

                logger.info(f"Кеш экспортирован в файл: {output_path}")
                return True

        except Exception as e:
            logger.error(f"Ошибка при экспорте кеша: {e}")
            return False 
