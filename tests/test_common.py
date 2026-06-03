import pytest
from unittest.mock import patch, AsyncMock

from dava.common import make_request
from dava.errors import RequestError


class TestMakeRequest:
    async def test_get_success(self):
        from aiohttp import web
        from aiohttp.test_utils import AioHTTPTestCase, TestServer

        async def handler(request):
            return web.json_response({"status": "ok"})

        app = web.Application()
        app.router.add_get("/test", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            result = await make_request(
                f"http://localhost:{server.port}/test",
                headers={},
                method="GET",
            )
            assert result == {"status": "ok"}
        finally:
            await server.close()

    async def test_post_success(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer

        async def handler(request):
            data = await request.json()
            return web.json_response({"received": data})

        app = web.Application()
        app.router.add_post("/test", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            result = await make_request(
                f"http://localhost:{server.port}/test",
                headers={},
                method="POST",
                data={"key": "value"},
            )
            assert result == {"received": {"key": "value"}}
        finally:
            await server.close()

    async def test_non_200_raises(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer

        async def handler(request):
            return web.Response(status=500, text="Internal Server Error")

        app = web.Application()
        app.router.add_get("/test", handler)
        server = TestServer(app)
        await server.start_server()
        try:
            with pytest.raises(RequestError, match="500"):
                await make_request(
                    f"http://localhost:{server.port}/test",
                    headers={},
                    method="GET",
                )
        finally:
            await server.close()

    async def test_network_error(self):
        with pytest.raises(RequestError, match="Network error"):
            await make_request(
                "http://localhost:1/nonexistent",
                headers={},
                method="GET",
            )