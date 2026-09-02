"""Tests for uniform API error responses (main.register_exception_handlers).

Uses a throwaway FastAPI app so the production app is never mutated.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.main import register_exception_handlers


def _client(app: FastAPI) -> TestClient:
    # 500 响应也要作为响应返回（而非在客户端侧重抛）才能断言其格式
    return TestClient(app, raise_server_exceptions=False)


def _make_app() -> FastAPI:
    test_app = FastAPI()
    register_exception_handlers(test_app)
    return test_app


def test_http_exception_uniform_detail():
    test_app = _make_app()

    @test_app.get("/missing")
    def missing():
        raise HTTPException(status_code=404, detail="项目不存在")

    response = _client(test_app).get("/missing")
    assert response.status_code == 404
    assert response.json() == {"detail": "项目不存在"}


def test_http_exception_validation_error_keeps_422():
    test_app = _make_app()

    @test_app.get("/bad")
    def bad():
        raise HTTPException(status_code=422, detail="参数不合法")

    response = _client(test_app).get("/bad")
    assert response.status_code == 422
    assert response.json() == {"detail": "参数不合法"}


def test_unhandled_exception_returns_500_uniform_json():
    test_app = _make_app()

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("disk exploded")

    response = _client(test_app).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "disk exploded"}


def test_unhandled_exception_detail_truncated():
    test_app = _make_app()

    @test_app.get("/long")
    def long_error():
        raise RuntimeError("x" * 2000)

    response = _client(test_app).get("/long")
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert len(detail) <= 500


def test_unhandled_exception_empty_message_fallback():
    test_app = _make_app()

    @test_app.get("/empty")
    def empty_error():
        raise ValueError()

    response = _client(test_app).get("/empty")
    assert response.status_code == 500
    assert response.json() == {"detail": "服务器内部错误"}
