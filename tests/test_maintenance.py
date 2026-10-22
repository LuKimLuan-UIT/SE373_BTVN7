"""Kiểm tra thao tác bảo trì trên dữ liệu tạm, không gọi model thật."""
import asyncio
import importlib

import httpx
import pytest

from memory_agent.memory.store import MarkdownMemoryStore
from tests.test_agent_memory import FakeToolChatModel, make_runtime
from langchain_core.messages import AIMessage


@pytest.fixture
def web(tmp_path, monkeypatch):
    module = importlib.import_module('memory_agent.ui.app')
    runtime = make_runtime(tmp_path, FakeToolChatModel(responses=[AIMessage(content='OK')]))
    monkeypatch.setattr(module, '_state', {'runtime': runtime})
    return module, runtime


def request(module, method, path, **kwargs):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url='http://127.0.0.1:8000') as client:
            return await client.request(method, path, **kwargs)
    return asyncio.run(send())


def test_clear_removes_active_and_superseded_but_preserves_other_users_and_sessions(web):
    module, runtime = web
    runtime.chat('s1', 'Chào')
    old = runtime.manager.remember('auth', 'JWT')
    runtime.manager.supersede(old['key'], 'Cookie')
    other = MarkdownMemoryStore(runtime.settings.memory_dir, 'u2')
    other.put(('memory', 'u2', 'auth'), 'other-key', {'content': 'Khác'})
    response = request(module, 'POST', '/api/memory/clear', json={'user_id': 'u1'})
    assert response.status_code == 200
    assert response.json()['deleted'] == 2
    assert runtime.manager.entries() == []
    assert 'Cookie' not in runtime.manager.index_text()
    assert runtime.history('s1')
    assert other.get(('memory', 'u2', 'auth'), 'other-key') is not None
    reopened = MarkdownMemoryStore(runtime.settings.memory_dir, 'u1')
    assert reopened.search(('memory', 'u1')) == []
    assert request(module, 'POST', '/api/memory/clear', json={'user_id': 'u1'}).json()['deleted'] == 0


def test_clear_rejects_wrong_user(web):
    module, runtime = web
    runtime.manager.remember('auth', 'JWT')
    assert request(module, 'POST', '/api/memory/clear', json={'user_id': 'u2'}).status_code == 409
    assert len(runtime.manager.entries()) == 1


def test_restart_schedules_real_process_restart_and_keeps_memory(web, monkeypatch):
    module, runtime = web
    runtime.manager.remember('auth', 'JWT')
    ports = []
    monkeypatch.setattr(module, 'schedule_restart', ports.append)
    health = request(module, 'GET', '/api/health').json()
    response = request(module, 'POST', '/api/server/restart')
    assert response.status_code == 200
    assert response.json()['previous_pid'] == health['pid']
    assert ports == [8000]
    assert len(runtime.manager.entries()) == 1
    assert request(module, 'POST', '/api/chat', json={'thread_id': 's2', 'message': 'Hi'}).status_code == 503


def test_restart_failure_keeps_runtime_available(web, monkeypatch):
    module, runtime = web
    def fail(port):
        raise OSError('Cannot start helper')
    monkeypatch.setattr(module, 'schedule_restart', fail)
    with pytest.raises(OSError):
        request(module, 'POST', '/api/server/restart')
    assert request(module, 'GET', '/api/health').json()['ok']
