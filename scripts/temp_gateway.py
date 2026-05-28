import uvicorn
from fastapi import FastAPI, Request, Response
import httpx
import asyncio

app = FastAPI(title="SignalixAI Local Gateway")

# Service ports
SERVICES = {
    "auth": "http://localhost:8000",
    "user": "http://localhost:8001",
    "analysis": "http://localhost:8002",
    "market": "http://localhost:8003",
    "portfolio": "http://localhost:8004",
    "notification": "http://localhost:8005",
}

async def proxy_request(service_url: str, path: str, request: Request):
    async with httpx.AsyncClient() as client:
        url = f"{service_url}{path}"
        if request.query_params:
            url = f"{url}?{request.query_params}"
        
        headers = dict(request.headers)
        # Remove host header to avoid issues
        headers.pop("host", None)
        
        content = await request.body()
        
        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=content,
                timeout=30.0
            )
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except Exception as e:
            return Response(content=f"Gateway Error: {str(e)}", status_code=502)

@app.api_route("/api/v1/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def auth_proxy(path: str, request: Request):
    return await proxy_request(SERVICES["auth"], f"/api/v1/auth/{path}", request)

@app.api_route("/api/v1/users/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def user_proxy(path: str, request: Request):
    # Map /api/v1/users/me to /api/v1/user/profile if needed
    backend_path = f"/api/v1/user/{path}"
    if path == "me":
        backend_path = "/api/v1/user/profile"
    return await proxy_request(SERVICES["user"], backend_path, request)

@app.api_route("/api/v1/analysis/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def analysis_proxy(path: str, request: Request):
    return await proxy_request(SERVICES["analysis"], f"/api/v1/analysis/{path}", request)

@app.api_route("/api/v1/market-data/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def market_proxy(path: str, request: Request):
    return await proxy_request(SERVICES["market"], f"/api/v1/market-data/{path}", request)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
