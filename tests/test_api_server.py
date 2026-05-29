import pytest
from fastapi import Request, Response

@pytest.mark.asyncio
async def test_csp_header_middleware():
    from core.api_server import add_csp_header

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": []
    }
    request = Request(scope)

    async def mock_call_next(req):
        return Response(content="test")

    response = await add_csp_header(request, mock_call_next)

    assert "Content-Security-Policy" in response.headers
    csp = response.headers["Content-Security-Policy"]

    assert "unsafe-eval" not in csp
    assert "unsafe-inline" not in csp
    assert "strict-dynamic" in csp
    assert "nonce-" in csp
    assert "default-src 'self'" in csp
