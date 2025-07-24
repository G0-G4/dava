import aiohttp
from typing import Dict, Any, Optional
from dava.errors import RequestError

async def make_request(
    url: str,
    headers: Dict[str, str],
    method: str = "POST",
    data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> dict:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            kwargs = {
                "headers": headers,
                "params": params,
                "json": data if method in ["POST", "PUT", "PATCH"] else None
            }
            
            async with session.request(method, url, **kwargs) as response:
                if response.status != 200:
                    error_msg = await response.text()
                    raise RequestError(f"{method} {url} failed: {response.status} - {error_msg}")
                return await response.json()
    except aiohttp.ClientError as e:
        raise RequestError(f"Network error: {str(e)}") from e
