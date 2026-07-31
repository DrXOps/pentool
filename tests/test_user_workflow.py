"""Интеграционный тест: симуляция работы пользователя.

Сценарий:
1. Запуск приложения
2. Создание нового проекта
3. Запуск прокси
4. Симуляция перехвата запроса
5. Отправка в Repeater (Ctrl+R)
6. Отправка запроса в Repeater (Ctrl+Space)
7. Проверка автосохранения вкладки
8. Закрытие и повторное открытие проекта
9. Проверка восстановления вкладок
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from pentool.api.proxy_api import InterceptedRequest, ProxyAPI
from pentool.core.database import init_db
from pentool.modules.proxy import ProxyServer
from pentool.services.proxy_service import ProxyService
from pentool.storage.http_storage import HttpStorage
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest.mark.asyncio
async def test_user_workflow_full():
    """Полный цикл работы пользователя с pentool."""

    # 1. Создаём временный проект (как "Ctrl+N → выбор пути")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_project.db")

        print(f"\n[USER] Создаю новый проект: {db_path}")
        await init_db(db_path)

        # 2. Инициализируем компоненты (как при старте приложения)
        print("[USER] Инициализирую ProxyService...")
        proxy = ProxyServer(
            host="127.0.0.1",
            port=8888,
            cert_dir=os.path.join(tmpdir, "certs"),
            db_path=db_path,
        )
        proxy_api = ProxyAPI()
        proxy_api.set_proxy(proxy)

        proxy_service = ProxyService(
            proxy_api=proxy_api,
            db_path=db_path,
        )

        # ВАЖНО: дождаться init_storage ДО любых других операций
        await proxy_service.init_storage()
        assert proxy_service.is_storage_ready(), "Storage должен быть готов после init"
        print("[USER] ✓ Storage готов")

        # 3. Симулируем перехват запроса (как будто proxy перехватил)
        print("[USER] Симулирую перехват GET http://example.com/test")
        from datetime import datetime, timezone
        req = InterceptedRequest(
            id="test-req-1",
            method="GET",
            url="http://example.com/test",
            headers={"Host": "example.com", "User-Agent": "Test"},
            body="",
            timestamp=datetime.now(timezone.utc),
            is_websocket=False,
        )

        # Сохраняем запрос (как ProxyScreen.add_request_row)
        row_id = await proxy_service.store_request(req)
        assert row_id is not None, "Запрос должен сохраниться"
        print(f"[USER] ✓ Запрос сохранён, row_id={row_id}")

        # 4. Проверяем что запрос появился в истории
        history = await proxy_service.get_history(limit=10)
        assert len(history) == 1, f"Должен быть 1 запрос в истории, получено {len(history)}"
        assert history[0]["method"] == "GET"
        assert history[0]["url"] == "http://example.com/test"
        print(f"[USER] ✓ История содержит 1 запрос: {history[0]['method']} {history[0]['url']}")

        # 5. Симулируем "Send to Repeater" (Ctrl+R на строке)
        print("[USER] Отправляю в Repeater (Ctrl+R)...")
        from pentool.utils.parser import build_http_request
        parsed_req = ParsedRequest(
            method="GET",
            url="http://example.com/test",
            headers={"Host": "example.com", "User-Agent": "Test"},
            body="",
        )
        raw_request = build_http_request(parsed_req)

        # RepeaterScreen.load_request_in_new_tab вызовет save_to_history
        from pentool.api.repeater_api import RepeaterAPI
        repeater_api = RepeaterAPI(db_path=db_path)

        # Симулируем отправку запроса (Ctrl+Space) и получение ответа
        print("[USER] Отправляю запрос (Ctrl+Space)...")
        response = ParsedResponse(
            status=200,
            headers={"Content-Type": "text/html"},
            body="<html>Test response</html>",
        )

        # Сохраняем в историю Repeater (автосохранение вкладки)
        entry_id = await repeater_api.save_to_history(parsed_req, response, tab_name="Tab 1")
        assert entry_id > 0, "Запись должна сохраниться в repeater_entries"
        print(f"[USER] ✓ Вкладка сохранена, entry_id={entry_id}")

        # 6. Проверяем что вкладка сохранилась
        repeater_history = await repeater_api.get_history(limit=10)
        assert len(repeater_history) == 1, f"Должна быть 1 вкладка, получено {len(repeater_history)}"
        assert repeater_history[0].tab_name == "Tab 1"
        assert repeater_history[0].method == "GET"
        assert repeater_history[0].url == "http://example.com/test"
        assert repeater_history[0].response_status == 200
        print(f"[USER] ✓ История Repeater содержит 1 вкладку: {repeater_history[0].tab_name}")

        # 7. Симулируем закрытие проекта (как Ctrl+Q)
        print("[USER] Закрываю приложение (Ctrl+Q)...")
        await proxy_service._storage.close()

        # 8. Симулируем повторное открытие проекта (Ctrl+O)
        print(f"[USER] Повторно открываю проект: {db_path}")

        # Пересоздаём ProxyService (как при switch_project)
        proxy_service2 = ProxyService(
            proxy_api=proxy_api,
            db_path=db_path,
        )

        # ВАЖНО: сначала init_storage
        await proxy_service2.init_storage()
        assert proxy_service2.is_storage_ready(), "Storage должен быть готов после повторного открытия"

        # Проверяем что история Proxy восстановилась
        history2 = await proxy_service2.get_history(limit=10)
        assert len(history2) == 1, f"История должна восстановиться, получено {len(history2)} записей"
        print(f"[USER] ✓ История Proxy восстановлена: {len(history2)} запрос(ов)")

        # Проверяем что вкладки Repeater восстановились
        repeater_api2 = RepeaterAPI(db_path=db_path)
        repeater_history2 = await repeater_api2.get_history(limit=10)
        assert len(repeater_history2) == 1, f"Вкладки должны восстановиться, получено {len(repeater_history2)}"
        assert repeater_history2[0].tab_name == "Tab 1"
        print(f"[USER] ✓ Вкладки Repeater восстановлены: {len(repeater_history2)} вкладка(и)")

        # 9. Проверяем switch_db (как при переключении проекта)
        print("[USER] Переключаюсь на другой проект...")
        db_path2 = os.path.join(tmpdir, "test_project2.db")
        await init_db(db_path2)

        # Дожидаемся завершения текущих операций перед switch
        await asyncio.sleep(0.1)

        # switch_db должен работать без ошибок
        await proxy_service2.switch_db(db_path2)
        assert proxy_service2.is_storage_ready(), "Storage должен быть готов после switch_db"

        # Новый проект должен быть пустым
        history3 = await proxy_service2.get_history(limit=10)
        assert len(history3) == 0, f"Новый проект должен быть пустым, получено {len(history3)} записей"
        print("[USER] ✓ Переключение на новый проект успешно (история пустая)")

        await proxy_service2._storage.close()

        print("\n[USER] ✅ ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО")


if __name__ == "__main__":
    asyncio.run(test_user_workflow_full())
