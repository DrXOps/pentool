"""Integration test: simulating the user workflow.

Scenario:
1. Application startup
2. Creating a new project
3. Starting the proxy
4. Simulating request interception
5. Sending to Repeater (Ctrl+R)
6. Sending the request in Repeater (Ctrl+Space)
7. Checking tab autosave
8. Closing and reopening the project
9. Checking tab restoration
"""

import asyncio
import os
import tempfile

import pytest

from pentool.api.proxy_api import InterceptedRequest, ProxyAPI
from pentool.core.db_schema import init_db
from pentool.modules.proxy import ProxyServer
from pentool.services.proxy_service import ProxyService
from pentool.utils.parser import ParsedRequest, ParsedResponse


@pytest.mark.asyncio
async def test_user_workflow_full():
    """Full user workflow cycle with pentool."""

    # 1. Create a temporary project (like "Ctrl+N → path selection")
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_project.db")

        print(f"\n[USER] Создаю новый проект: {db_path}")
        await init_db(db_path)

        # 2. Initialize the components (as on application startup)
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

        # IMPORTANT: wait for init_storage BEFORE any other operations
        await proxy_service.init_storage()
        assert proxy_service.is_storage_ready(), "Storage должен быть готов после init"
        print("[USER] ✓ Storage готов")

        # 3. Simulate request interception (as if the proxy intercepted it)
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

        # Save the request (like ProxyScreen.add_request_row)
        row_id = await proxy_service.store_request(req)
        assert row_id is not None, "Запрос должен сохраниться"
        print(f"[USER] ✓ Запрос сохранён, row_id={row_id}")

        # 4. Check that the request appeared in history
        history = await proxy_service.get_history(limit=10)
        assert len(history) == 1, f"Должен быть 1 запрос в истории, получено {len(history)}"
        assert history[0]["method"] == "GET"
        assert history[0]["url"] == "http://example.com/test"
        print(f"[USER] ✓ История содержит 1 запрос: {history[0]['method']} {history[0]['url']}")

        # 5. Simulate "Send to Repeater" (Ctrl+R on the row)
        print("[USER] Отправляю в Repeater (Ctrl+R)...")
        from pentool.utils.parser import build_http_request

        parsed_req = ParsedRequest(
            method="GET",
            url="http://example.com/test",
            headers={"Host": "example.com", "User-Agent": "Test"},
            body="",
        )
        _raw_request = build_http_request(parsed_req)

        # RepeaterScreen.load_request_in_new_tab will call save_to_history
        from pentool.api.repeater_api import RepeaterAPI

        repeater_api = RepeaterAPI(db_path=db_path)

        # Simulate sending the request (Ctrl+Space = ctrl-at in the terminal) and receiving a response
        print("[USER] Отправляю запрос (Ctrl+Space / ctrl-at)...")
        response = ParsedResponse(
            status=200,
            headers={"Content-Type": "text/html"},
            body="<html>Test response</html>",
        )

        # Save to Repeater history (tab autosave)
        entry_id = await repeater_api.save_to_history(parsed_req, response, tab_name="Tab 1")
        assert entry_id > 0, "Запись должна сохраниться в repeater_entries"
        print(f"[USER] ✓ Вкладка сохранена, entry_id={entry_id}")

        # 6. Check that the tab was saved
        repeater_history = await repeater_api.get_history(limit=10)
        assert len(repeater_history) == 1, f"Должна быть 1 вкладка, получено {len(repeater_history)}"
        assert repeater_history[0].tab_name == "Tab 1"
        assert repeater_history[0].method == "GET"
        assert repeater_history[0].url == "http://example.com/test"
        assert repeater_history[0].response_status == 200
        print(f"[USER] ✓ История Repeater содержит 1 вкладку: {repeater_history[0].tab_name}")

        # 7. Simulate closing the project (like Ctrl+Q)
        print("[USER] Закрываю приложение (Ctrl+Q)...")
        await proxy_service._storage.close()

        # 8. Simulate reopening the project (Ctrl+O)
        print(f"[USER] Повторно открываю проект: {db_path}")

        # Recreate ProxyService (as during switch_project)
        proxy_service2 = ProxyService(
            proxy_api=proxy_api,
            db_path=db_path,
        )

        # IMPORTANT: init_storage first
        await proxy_service2.init_storage()
        assert proxy_service2.is_storage_ready(), "Storage должен быть готов после повторного открытия"

        # Check that the Proxy history has been restored
        history2 = await proxy_service2.get_history(limit=10)
        assert len(history2) == 1, f"История должна восстановиться, получено {len(history2)} записей"
        print(f"[USER] ✓ История Proxy восстановлена: {len(history2)} запрос(ов)")

        # Check that the Repeater tabs have been restored
        repeater_api2 = RepeaterAPI(db_path=db_path)
        repeater_history2 = await repeater_api2.get_history(limit=10)
        assert len(repeater_history2) == 1, f"Вкладки должны восстановиться, получено {len(repeater_history2)}"
        assert repeater_history2[0].tab_name == "Tab 1"
        print(f"[USER] ✓ Вкладки Repeater восстановлены: {len(repeater_history2)} вкладка(и)")

        # 9. Check switch_db (as when switching projects)
        print("[USER] Переключаюсь на другой проект...")
        db_path2 = os.path.join(tmpdir, "test_project2.db")
        await init_db(db_path2)

        # Wait for the current operations to finish before the switch
        await asyncio.sleep(0.1)

        # switch_db must work without errors
        await proxy_service2.switch_db(db_path2)
        assert proxy_service2.is_storage_ready(), "Storage должен быть готов после switch_db"

        # The new project must be empty
        history3 = await proxy_service2.get_history(limit=10)
        assert len(history3) == 0, f"Новый проект должен быть пустым, получено {len(history3)} записей"
        print("[USER] ✓ Переключение на новый проект успешно (история пустая)")

        await proxy_service2._storage.close()

        print("\n[USER] ✅ ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО")


if __name__ == "__main__":
    asyncio.run(test_user_workflow_full())
