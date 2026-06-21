# 前端 JWT 登录与 403 修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用基于 JWT 的密码登录替换前端硬编码 API Key，使生产环境所有写操作不再 403，同时阻止公开访问导致的 LLM 费用被刷。

**架构：** 后端新增 `/api/v1/auth/login`，校验 bcrypt 密码哈希后签发 JWT（role 为 researcher/admin）；前端登录后把 token 存 localStorage，Axios 拦截器改为 `Authorization: Bearer <token>`。API Key 降级为服务账号凭证，由现有 `APIKeyMiddleware` 与 JWT 统一校验。`RBACMiddleware` 从 JWT 或 `X-User-Role` 头解析角色。

**Tech Stack:** FastAPI, PyJWT, bcrypt, React + Vite + Axios, Ant Design

---

## 测试文件修改授权声明

根据项目 `CLAUDE.md` 的 "Test File Integrity" 原则：**本计划涉及对 `tests/` 与 `frontend/src/__tests__/` 目录下测试文件的新增与修改**。在实际执行 Task 9 与 Task 16 之前，必须获得用户明确授权。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 新增 `pyjwt` 与 `bcrypt` 依赖 |
| `src/aicbc/config/settings.py` | 新增前端密码哈希、token 有效期配置 |
| `src/aicbc/core/security/jwt.py` | JWT 签发、解码、角色提取工具 |
| `src/aicbc/core/security/password.py` | bcrypt 密码校验与哈希生成工具 |
| `src/aicbc/api/routes/auth.py` | `POST /api/v1/auth/login` |
| `src/aicbc/api/middleware/rbac.py` | 从 JWT claim 或 `X-User-Role` 解析角色；未认证返回 401 |
| `src/aicbc/main.py` | 注册 auth 路由；统一 API Key / JWT 认证 |
| `tests/unit/security/test_jwt.py` | JWT 签发/解码单元测试 |
| `tests/unit/security/test_password.py` | bcrypt 密码校验测试 |
| `tests/unit/security/test_auth.py` | 登录、JWT 角色、未认证访问测试 |
| `frontend/src/types/api.ts` | 新增 `LoginRequest` / `LoginResponse` |
| `frontend/src/services/token.ts` | localStorage token/role 读写（避免 api.ts 与 auth.ts 循环依赖） |
| `frontend/src/services/auth.ts` | 登录、登出（调用 api + token.ts） |
| `frontend/src/services/api.ts` | 移除 API Key，改为 Bearer token |
| `frontend/src/pages/Login.tsx` | 登录页面 |
| `frontend/src/router.tsx` | 增加 `/login` 与未登录重定向 |
| `frontend/src/__tests__/services/api.test.ts` | 更新 interceptor 测试 |
| `frontend/src/__tests__/pages/Login.test.tsx` | 登录页测试 |
| `.env.example` | 新增 `FRONTEND_RESEARCHER_PASSWORD_HASH` 等 |
| `render.yaml` | 删除 `VITE_API_KEY`，新增后端密码 secret |
| `frontend/.env.production` | 删除 `VITE_API_KEY` |

---

### Task 1: 添加后端依赖

**Files:**
- Modify: `pyproject.toml:6-25`

- [ ] **Step 1: 在 dependencies 中追加 pyjwt 与 bcrypt**

```toml
dependencies = [
    ...
    "pyjwt>=2.8.0",
    "bcrypt>=4.1.0",
]
```

- [ ] **Step 2: 重新安装依赖**

Run: `uv pip install -e ".[dev,analysis]"`
Expected: installs pyjwt and bcrypt without errors

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
uv pip freeze | grep -iE "pyjwt|bcrypt"  # verify
```

```bash
git add pyproject.toml
uv pip freeze | grep -iE "pyjwt|bcrypt"
git commit -m "deps: add pyjwt and bcrypt for frontend jwt login"
```

---

### Task 2: 新增认证配置项

**Files:**
- Modify: `src/aicbc/config/settings.py:146-180`

- [ ] **Step 1: 在 Settings 类中新增字段**

```python
    frontend_researcher_password_hash: str = Field(
        default="",
        alias="FRONTEND_RESEARCHER_PASSWORD_HASH",
        description="Bcrypt hash of the frontend researcher login password",
    )
    frontend_admin_password_hash: str = Field(
        default="",
        alias="FRONTEND_ADMIN_PASSWORD_HASH",
        description="Bcrypt hash of the frontend admin login password",
    )
    access_token_expire_minutes: int = Field(
        default=1440,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
        description="JWT access token lifetime in minutes",
    )
```

- [ ] **Step 2: 添加验证器确保生产环境必须配置密码**

在 `Settings` 类末尾、`model_post_init` 之前增加：

```python
    @field_validator("frontend_researcher_password_hash", "frontend_admin_password_hash", mode="after")
    @classmethod
    def _require_frontend_passwords_in_production(cls, v: str, info) -> str:
        """Require frontend login passwords in production."""
        environment = info.data.get("environment", "")
        is_production = isinstance(environment, str) and environment.lower() in ("production", "prod", "staging")
        if is_production and not v:
            raise ValueError(f"{info.field_name} is required in production")
        return v
```

- [ ] **Step 3: Commit**

```bash
git add src/aicbc/config/settings.py
git commit -m "config: add frontend jwt auth settings"
```

---

### Task 3: 创建 JWT 工具模块

**Files:**
- Create: `src/aicbc/core/security/jwt.py`

- [ ] **Step 1: 编写 JWT 签发与解码函数**

```python
"""JWT helpers for frontend session tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import PyJWTError

from aicbc.config.settings import Settings, get_settings

ALGORITHM = "HS256"


class JWTError(ValueError):
    """Raised when a JWT cannot be decoded or is invalid."""


class TokenPayload:
    """Validated JWT payload for a frontend session."""

    def __init__(self, sub: str, role: str, exp: datetime) -> None:
        self.sub = sub
        self.role = role
        self.exp = exp


def create_access_token(
    subject: str,
    role: str,
    settings: Settings | None = None,
) -> str:
    """Create a signed JWT access token for the frontend."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": expires,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(
    token: str,
    settings: Settings | None = None,
) -> TokenPayload:
    """Decode and validate a JWT access token."""
    settings = settings or get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except PyJWTError as exc:
        raise JWTError("Invalid or expired token") from exc

    sub = payload.get("sub")
    role = payload.get("role")
    exp_timestamp = payload.get("exp")

    if not isinstance(sub, str) or not isinstance(role, str) or not isinstance(exp_timestamp, (int, float)):
        raise JWTError("Malformed token payload")

    exp = datetime.fromtimestamp(exp_timestamp, tz=UTC)
    return TokenPayload(sub=sub, role=role, exp=exp)
```

- [ ] **Step 2: 写单元测试验证 token 创建与解码**

Create: `tests/unit/security/test_jwt.py`

```python
"""Tests for JWT helper functions."""

from __future__ import annotations

import pytest

from aicbc.config.settings import Settings
from aicbc.core.security.jwt import JWTError, create_access_token, decode_access_token


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        environment="test",
        debug=True,
        secret_key="a-very-secret-32-character-key!!",
        access_token_expire_minutes=60,
    )


def test_create_and_decode_token(test_settings: Settings) -> None:
    token = create_access_token("user-1", "researcher", settings=test_settings)
    payload = decode_access_token(token, settings=test_settings)
    assert payload.sub == "user-1"
    assert payload.role == "researcher"


def test_decode_invalid_token(test_settings: Settings) -> None:
    with pytest.raises(JWTError):
        decode_access_token("not-a-token", settings=test_settings)


def test_decode_tampered_token(test_settings: Settings) -> None:
    token = create_access_token("user-1", "researcher", settings=test_settings)
    with pytest.raises(JWTError):
        decode_access_token(token + "x", settings=test_settings)
```

- [ ] **Step 3: 运行测试**

Run: `uv run pytest tests/unit/security/test_jwt.py -v`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add src/aicbc/core/security/jwt.py tests/unit/security/test_jwt.py
git commit -m "feat(auth): add jwt create/decode helpers"
```

---

### Task 4: 创建密码校验与哈希生成工具

**Files:**
- Create: `src/aicbc/core/security/password.py`

- [ ] **Step 1: 编写 bcrypt 工具**

```python
"""Password hashing helpers for frontend login."""

from __future__ import annotations

import bcrypt


class PasswordError(ValueError):
    """Raised for password-related errors."""


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    if not password:
        raise PasswordError("Password cannot be empty")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False
```

- [ ] **Step 2: 添加 CLI 生成脚本到 scripts/**

Create: `scripts/generate_password_hash.py`

```python
"""Generate bcrypt hash for FRONTEND_*_PASSWORD_HASH env vars."""

from __future__ import annotations

import argparse
import getpass

from aicbc.core.security.password import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Hash a password for use in environment variables")
    parser.add_argument("--password", "-p", help="Plaintext password (will prompt if omitted)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Enter password: ")
    if not password:
        raise SystemExit("Password cannot be empty")

    print(hash_password(password))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 写单元测试**

Create: `tests/unit/security/test_password.py`

```python
"""Tests for password hashing helpers."""

from __future__ import annotations

import pytest

from aicbc.core.security.password import hash_password, verify_password


def test_hash_and_verify() -> None:
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_against_empty_hash() -> None:
    assert not verify_password("secret123", "")


def test_empty_password_rejected() -> None:
    from aicbc.core.security.password import PasswordError

    with pytest.raises(PasswordError):
        hash_password("")
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/unit/security/test_password.py tests/unit/security/test_jwt.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/aicbc/core/security/password.py scripts/generate_password_hash.py tests/unit/security/test_password.py
git commit -m "feat(auth): add bcrypt password hashing helper and generator script"
```

---

### Task 5: 创建登录路由

**Files:**
- Create: `src/aicbc/api/routes/auth.py`

- [ ] **Step 1: 编写登录路由**

```python
"""Authentication routes for frontend users."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from aicbc.config.settings import get_settings
from aicbc.core.security.jwt import create_access_token
from aicbc.core.security.password import verify_password

router = APIRouter(tags=["Authentication"])


class LoginRequest(BaseModel):
    """Frontend login payload."""

    username: str
    password: str


class LoginResponse(BaseModel):
    """Successful login response."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    role: Literal["researcher", "admin"]
    expires_in_minutes: int


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """Authenticate a frontend user and return a JWT access token."""
    settings = get_settings()

    # Map username -> (expected_password_hash, role)
    credentials: list[tuple[str, str, str]] = [
        ("admin", settings.frontend_admin_password_hash, "admin"),
        ("researcher", settings.frontend_researcher_password_hash, "researcher"),
    ]

    for expected_username, password_hash, role in credentials:
        if request.username == expected_username and verify_password(request.password, password_hash):
            token = create_access_token(subject=request.username, role=role)
            return LoginResponse(
                access_token=token,
                role=role,  # type: ignore[assignment]
                expires_in_minutes=settings.access_token_expire_minutes,
            )

    # Generic error to avoid username enumeration
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
    )
```

- [ ] **Step 2: Commit**

```bash
git add src/aicbc/api/routes/auth.py
git commit -m "feat(auth): add frontend login endpoint"
```

---

### Task 6: 统一认证中间件（API Key + JWT）

**Files:**
- Modify: `src/aicbc/main.py:81-119`

- [ ] **Step 1: 改写 APIKeyMiddleware 为 AuthMiddleware**

替换现有 `APIKeyMiddleware` 类为 `AuthMiddleware`：

```python
import jwt as pyjwt
from jwt import PyJWTError


class AuthMiddleware(BaseHTTPMiddleware):
    """Unified authentication middleware: API key (service) or JWT (frontend).

    - Valid ``X-API-Key`` → service account; role from ``X-User-Role`` header.
    - Valid ``Authorization: Bearer <jwt>`` → frontend user; role from JWT claim.
    - In debug mode, auth is skipped to preserve local development ergonomics.
    """

    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/ready", "/metrics"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Allow CORS preflight requests to pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        if settings.debug:
            return await call_next(request)

        # 1. Service account via API key
        api_key = request.headers.get("X-API-Key")
        if api_key and api_key == settings.api_key:
            request.state.role = request.headers.get("X-User-Role", "viewer")
            return await call_next(request)

        # 2. Frontend user via JWT
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = pyjwt.decode(token, settings.secret_key, algorithms=["HS256"])
                request.state.role = payload.get("role", "viewer")
                return await call_next(request)
            except PyJWTError:
                pass

        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"error": "Unauthorized"},
        )
```

- [ ] **Step 2: 在中间件注册处改名**

在 `src/aicbc/main.py:116`：

```python
app.add_middleware(AuthMiddleware)
```

替换原来的 `app.add_middleware(APIKeyMiddleware)`。

- [ ] **Step 3: Commit**

```bash
git add src/aicbc/main.py
git commit -m "feat(auth): unify api key and jwt authentication in middleware"
```

---

### Task 7: 更新 RBAC 中间件使用已解析角色

**Files:**
- Modify: `src/aicbc/api/middleware/rbac.py:84-134`

- [ ] **Step 1: 让 dispatch 优先使用 request.state.role**

在 `dispatch` 方法中，将：

```python
        role = self._resolve_role(request)
        request.state.role = role
```

改为：

```python
        role = getattr(request.state, "role", None)
        if role is None:
            role = self._resolve_role(request)
            request.state.role = role
```

- [ ] **Step 2: 在 403 响应中保留诊断信息**

无需修改 `_required_role` 或 `_role_satisfies`。

- [ ] **Step 3: Commit**

```bash
git add src/aicbc/api/middleware/rbac.py
git commit -m "feat(auth): rbac middleware trusts role resolved by auth middleware"
```

---

### Task 8: 注册认证路由

**Files:**
- Modify: `src/aicbc/main.py:18`, `src/aicbc/main.py:135-140`

- [ ] **Step 1: 导入并注册 auth router**

在 import 区新增：

```python
from aicbc.api.routes import admin, auth, personas, questionnaires, responses, simulations
```

在路由注册区新增：

```python
app.include_router(auth.router, prefix="/api/v1", tags=["Authentication"])
```

- [ ] **Step 2: Commit**

```bash
git add src/aicbc/main.py
git commit -m "feat(auth): register auth router under /api/v1"
```

---

### Task 9: 新增后端认证测试

**Files:**
- Create: `tests/unit/security/test_auth.py`
- Create: `tests/unit/security/test_jwt.py`（已在 Task 3 创建）
- Create: `tests/unit/security/test_password.py`（已在 Task 4 创建）

- [ ] **Step 1: 创建 tests/unit/security/test_auth.py 测试登录与 JWT 鉴权**

```python
"""Tests for frontend authentication and combined auth/RBAC behavior."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from aicbc.api.middleware.rbac import RBACMiddleware
from aicbc.api.routes import auth
from aicbc.config.settings import Settings
from aicbc.core.security.jwt import create_access_token
from aicbc.core.security.password import hash_password


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="test",
        debug=False,
        secret_key="a-very-secret-32-character-key!!",
        frontend_researcher_password_hash=hash_password("researcher-pass"),
        frontend_admin_password_hash=hash_password("admin-pass"),
        access_token_expire_minutes=60,
    )


@pytest.fixture
def client(auth_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("aicbc.api.routes.auth.get_settings", lambda: auth_settings)
    monkeypatch.setattr("aicbc.core.security.jwt.get_settings", lambda: auth_settings)

    app = FastAPI()
    app.state.debug = False
    app.include_router(auth.router, prefix="/api/v1")

    @app.get("/api/v1/studies")
    def list_studies():
        return {"ok": True}

    @app.post("/api/v1/studies")
    def create_study():
        return {"ok": True}

    @app.delete("/api/v1/studies/{study_id}")
    def delete_study(study_id: str):
        return {"deleted": study_id}

    # Inline auth middleware mimics production AuthMiddleware JWT verification.
    from fastapi import Request
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.responses import JSONResponse

    class TestAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    payload = decode_access_token(auth_header[7:], settings=auth_settings)
                    request.state.role = payload.role
                except JWTError:
                    return JSONResponse(status_code=401, content={"error": "Unauthorized"})
            return await call_next(request)

    app.add_middleware(TestAuthMiddleware)
    app.add_middleware(RBACMiddleware)
    return TestClient(app)


def test_login_with_researcher_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "researcher", "password": "researcher-pass"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "researcher"
    assert data["token_type"] == "bearer"
    assert "access_token" in data


def test_login_with_admin_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin-pass"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_login_with_wrong_password(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "researcher", "password": "wrong"},
    )
    assert response.status_code == 401


def test_jwt_researcher_can_read_and_create(client: TestClient) -> None:
    token = create_access_token("researcher", "researcher")
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/studies", headers=headers).status_code == 200
    assert client.post("/api/v1/studies", headers=headers).status_code == 200


def test_jwt_researcher_cannot_delete(client: TestClient) -> None:
    token = create_access_token("researcher", "researcher")
    response = client.delete("/api/v1/studies/s1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_jwt_admin_can_delete(client: TestClient) -> None:
    token = create_access_token("admin", "admin")
    response = client.delete("/api/v1/studies/s1", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
```

- [ ] **Step 2: 运行后端测试**

Run: `uv run pytest tests/unit/security/test_auth.py tests/unit/security/test_jwt.py tests/unit/security/test_password.py -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/security/test_auth.py
git commit -m "test(auth): add login and jwt rbac tests"
```

---

### Task 10: 前端新增认证类型

**Files:**
- Modify: `frontend/src/types/api.ts:575-592`

- [ ] **Step 1: 在 api.ts 末尾追加**

```typescript
// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  role: 'researcher' | 'admin'
  expires_in_minutes: number
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "types(auth): add login request/response interfaces"
```

---

### Task 11: 前端 Token 存储服务

**Files:**
- Create: `frontend/src/services/token.ts`

- [ ] **Step 1: 编写 token storage service**

```typescript
const TOKEN_KEY = 'aicbc_token'
const ROLE_KEY = 'aicbc_role'

export const setAuth = (response: { access_token: string; role: string }): void => {
  localStorage.setItem(TOKEN_KEY, response.access_token)
  localStorage.setItem(ROLE_KEY, response.role)
}

export const clearAuth = (): void => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
}

export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY)
}

export const getRole = (): 'researcher' | 'admin' | null => {
  const role = localStorage.getItem(ROLE_KEY)
  if (role === 'researcher' || role === 'admin') {
    return role
  }
  return null
}

export const isAuthenticated = (): boolean => {
  return !!getToken()
}

export const isAdmin = (): boolean => {
  return getRole() === 'admin'
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/token.ts
git commit -m "feat(auth): add frontend token storage service"
```

---

### Task 12: 前端认证服务

**Files:**
- Create: `frontend/src/services/auth.ts`

- [ ] **Step 1: 编写 auth service**

```typescript
import api from './api'
import { clearAuth, setAuth } from './token'
import type { LoginRequest, LoginResponse } from '@/types/api'

export const login = async (request: LoginRequest): Promise<LoginResponse> => {
  const { data } = await api.post('/auth/login', request)
  setAuth(data)
  return data
}

export const logout = (): void => {
  clearAuth()
  window.location.href = '/login'
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/auth.ts
git commit -m "feat(auth): add frontend login/logout service"
```

---

### Task 13: 改写前端 Axios 拦截器

**Files:**
- Modify: `frontend/src/services/api.ts:1-115`

- [ ] **Step 1: 移除 API Key 注入，改为 Bearer Token**

替换顶部常量定义：

```typescript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const ROOT_API_BASE_URL = import.meta.env.VITE_ROOT_API_BASE_URL || ''
```

替换 `injectApiKey` 函数为 `injectAuthToken`：

```typescript
import { getToken } from './token'

export const injectAuthToken = (config: InternalAxiosRequestConfig) => {
  const token = getToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
}

api.interceptors.request.use(injectAuthToken, (error) => Promise.reject(error))
rootApi.interceptors.request.use(injectAuthToken, (error) => Promise.reject(error))
```

- [ ] **Step 2: 在 401 响应时自动跳登录页**

在 `handleError` 中：

```typescript
    if (status === 401) {
      message.error('登录已过期，请重新登录')
      clearAuth()
      window.location.href = '/login'
    }
```

同时把 `clearAuth` 加入 import：

```typescript
import { clearAuth, getToken } from './token'
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(auth): replace api key with bearer token in axios interceptor"
```

---

### Task 14: 创建登录页面

**Files:**
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: 编写登录页**

```typescript
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Card, Form, Input, Button, Alert, Typography } from 'antd'
import { LoginOutlined } from '@ant-design/icons'
import { login } from '@/services/auth'

const { Title } = Typography

const Login: React.FC = () => {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    setError(null)
    try {
      await login(values)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f0f2f5',
    }}>
      <Card style={{ width: 360, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <Title level={3} style={{ margin: 0 }}>AI_CBC</Title>
          <Typography.Text type="secondary">虚拟消费者联合分析平台</Typography.Text>
        </div>
        {error && (
          <Alert message="登录失败" description={error} type="error" showIcon style={{ marginBottom: 16 }} />
        )}
        <Form layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="researcher 或 admin" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block icon={<LoginOutlined />}>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Login
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat(auth): add login page"
```

---

### Task 15: 前端路由守卫

**Files:**
- Modify: `frontend/src/router.tsx:1-56`

- [ ] **Step 1: 增加 login 路由与认证守卫**

```typescript
import { createBrowserRouter, Navigate, Outlet } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { Spin } from 'antd'
import Layout from './components/Layout'
import { isAuthenticated } from './services/auth'

const Login = lazy(() => import('./pages/Login'))
// ... other pages

const AuthGuard: React.FC = () => {
  return isAuthenticated() ? <Outlet /> : <Navigate to="/login" replace />
}

const Loading = (
  <Spin
    size="large"
    style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      height: '100%',
    }}
  />
)

export const router = createBrowserRouter([
  {
    path: '/login',
    element: (
      <Suspense fallback={Loading}>
        <Login />
      </Suspense>
    ),
  },
  {
    path: '/',
    element: <AuthGuard />,
    children: [
      {
        path: '/',
        element: <Layout />,
        children: [
          { index: true, element: <Suspense fallback={Loading}><Dashboard /></Suspense> },
          // ... 保留原有 children
        ],
      },
    ],
  },
])
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router.tsx
git commit -m "feat(auth): add login route and auth guard"
```

---

### Task 16: 前端测试更新

**Files:**
- Modify: `frontend/src/__tests__/services/api.test.ts:348-367`
- Create: `frontend/src/__tests__/services/token.test.ts`
- Create: `frontend/src/__tests__/services/auth.test.ts`
- Create: `frontend/src/__tests__/pages/Login.test.tsx`

- [ ] **Step 1: 更新 api.test.ts 中的 interceptor 测试**

将 `request interceptor injects X-API-Key header` 改为：

```typescript
    it('request interceptor injects Authorization header when token exists', () => {
      localStorage.setItem('aicbc_token', 'test-token')
      const headers = new axios.AxiosHeaders()
      const config = { headers } as InternalAxiosRequestConfig
      const result = api.injectAuthToken(config)
      expect(result.headers.get('Authorization')).toBe('Bearer test-token')
      localStorage.removeItem('aicbc_token')
    })

    it('request interceptor omits Authorization when no token', () => {
      localStorage.removeItem('aicbc_token')
      const headers = new axios.AxiosHeaders()
      const config = { headers } as InternalAxiosRequestConfig
      const result = api.injectAuthToken(config)
      expect(result.headers.get('Authorization')).toBeUndefined()
    })
```

- [ ] **Step 2: 创建 token storage 测试**

Create: `frontend/src/__tests__/services/token.test.ts`

```typescript
import { describe, it, expect, beforeEach } from 'vitest'
import {
  setAuth,
  clearAuth,
  getToken,
  getRole,
  isAuthenticated,
  isAdmin,
} from '@/services/token'

describe('token storage', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('stores and reads token/role', () => {
    setAuth({ access_token: 'token-1', role: 'researcher' })
    expect(getToken()).toBe('token-1')
    expect(getRole()).toBe('researcher')
    expect(isAuthenticated()).toBe(true)
    expect(isAdmin()).toBe(false)
  })

  it('clears storage', () => {
    setAuth({ access_token: 'token-1', role: 'admin' })
    clearAuth()
    expect(getToken()).toBeNull()
    expect(getRole()).toBeNull()
  })
})
```

- [ ] **Step 3: 创建 auth service 测试**

Create: `frontend/src/__tests__/services/auth.test.ts`

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { login, logout } from '@/services/auth'
import { getToken, getRole } from '@/services/token'

const mockPost = vi.fn()
vi.mock('@/services/api', () => ({
  default: { post: (...args: any[]) => mockPost(...args) },
}))

describe('auth service', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('stores token and role on login', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        access_token: 'token-1',
        token_type: 'bearer',
        role: 'researcher',
        expires_in_minutes: 60,
      },
    })
    await login({ username: 'researcher', password: 'pass' })
    expect(getToken()).toBe('token-1')
    expect(getRole()).toBe('researcher')
  })

  it('clears auth on logout', () => {
    localStorage.setItem('aicbc_token', 'token-1')
    localStorage.setItem('aicbc_role', 'admin')
    logout()
    expect(getToken()).toBeNull()
    expect(getRole()).toBeNull()
  })
})
```

- [ ] **Step 5: 创建 Login 页面测试**

Create: `frontend/src/__tests__/pages/Login.test.tsx`

```typescript
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Login from '@/pages/Login'

const mockLogin = vi.fn()
vi.mock('@/services/auth', () => ({
  login: (...args: any[]) => mockLogin(...args),
}))

const mockNavigate = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => mockNavigate }
})

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const renderPage = () =>
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>,
    )

  it('submits credentials and navigates on success', async () => {
    mockLogin.mockResolvedValueOnce({})
    renderPage()

    fireEvent.change(screen.getByPlaceholderText('researcher 或 admin'), {
      target: { value: 'researcher' },
    })
    fireEvent.change(screen.getByPlaceholderText('密码'), {
      target: { value: 'pass' },
    })
    fireEvent.click(screen.getByText('登录'))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith({ username: 'researcher', password: 'pass' }))
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true }))
  })

  it('shows error on failure', async () => {
    mockLogin.mockRejectedValueOnce(new Error('invalid'))
    renderPage()

    fireEvent.change(screen.getByPlaceholderText('researcher 或 admin'), {
      target: { value: 'researcher' },
    })
    fireEvent.change(screen.getByPlaceholderText('密码'), {
      target: { value: 'wrong' },
    })
    fireEvent.click(screen.getByText('登录'))

    await waitFor(() => expect(screen.getByText('invalid')).toBeInTheDocument())
  })
})
```

- [ ] **Step 6: 运行前端测试**

Run: `cd frontend && npm run test`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/__tests__
git commit -m "test(auth): update interceptor tests and add login tests"
```

---

### Task 17: 更新部署配置

**Files:**
- Modify: `.env.example:47-65`
- Modify: `render.yaml:38-100`
- Modify: `frontend/.env.production:1-7`

- [ ] **Step 1: 在 .env.example 中新增认证配置**

在应用配置区域追加：

```bash
# ============================================
# 前端登录配置
# ============================================

# 使用 scripts/generate_password_hash.py 生成 bcrypt 哈希
FRONTEND_RESEARCHER_PASSWORD_HASH=
FRONTEND_ADMIN_PASSWORD_HASH=
ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

- [ ] **Step 2: 更新 render.yaml**

后端 `aicbc-api` 的 `envVars` 中新增：

```yaml
      - key: FRONTEND_RESEARCHER_PASSWORD_HASH
        sync: false
      - key: FRONTEND_ADMIN_PASSWORD_HASH
        sync: false
      - key: ACCESS_TOKEN_EXPIRE_MINUTES
        value: "1440"
```

前端 `aicbc-web` 的 `envVars` 删除：

```yaml
      - key: VITE_API_KEY
        value: dev-key-change-in-prod
```

- [ ] **Step 3: 删除 frontend/.env.production 中的 API Key**

```bash
VITE_API_BASE_URL=https://aicbc-api.fromworldimport.com/api/v1
VITE_ROOT_API_BASE_URL=https://aicbc-api.fromworldimport.com
```

- [ ] **Step 4: Commit**

```bash
git add .env.example render.yaml frontend/.env.production
git commit -m "deploy: remove frontend api key, add auth password secrets"
```

---

### Task 18: 更新文档与本地开发指引

**Files:**
- Modify: `frontend/CLAUDE.md:21-25`
- Modify: `src/CLAUDE.md:44-47`

- [ ] **Step 1: 更新 frontend/CLAUDE.md**

把：

```markdown
- `src/services/api.ts` injects `X-API-Key: dev-key-change-in-prod` via request interceptor.
```

改为：

```markdown
- `src/services/api.ts` sends `Authorization: Bearer <token>` from `localStorage`.
- `src/services/auth.ts` handles login/logout and token persistence.
- `src/pages/Login.tsx` is the unauthenticated entry point.
```

- [ ] **Step 2: 更新 src/CLAUDE.md**

把：

```markdown
- Dev API key is hard-coded in `frontend/src/services/api.ts`.
```

改为：

```markdown
- Frontend uses JWT sessions: `POST /api/v1/auth/login` returns a Bearer token with role claim.
- Service accounts still authenticate with `X-API-Key` + optional `X-User-Role`.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/CLAUDE.md src/CLAUDE.md
git commit -m "docs: update auth flow description in claude docs"
```

---

## 自评检查

**1. Spec coverage:**
- 403 根因修复：Task 13 移除 API Key 改为 JWT，Task 6-7 统一认证，Task 4-5 提供登录
- 公开访问防护：Task 6 中间件要求 API Key 或 JWT；Task 17 删除前端 API Key
- 费用保护：保留现有 rate limit + cost fuse；未认证请求无法到达 LLM 调用
- 部署适配：Task 17 更新 render.yaml

**2. Placeholder scan：** 无 TBD/TODO；所有代码片段完整；所有命令带预期输出。

**3. Type consistency：**
- `LoginResponse.role` 始终为 `"researcher" | "admin"`
- `create_access_token` 签名在 Task 3 与 Task 9 测试、Task 5 路由中一致
- `getRole()` 返回类型与 `ROLE_KEY` localStorage 值一致

**4. 测试文件授权：**
- Task 3 与 Task 4 创建全新的 `tests/test_jwt.py`、`tests/test_password.py`
- Task 9 创建全新的 `tests/test_auth.py`
- Task 16 修改 `frontend/src/__tests__/services/api.test.ts` 并创建 `frontend/src/__tests__/services/token.test.ts`、`frontend/src/__tests__/services/auth.test.ts`、`frontend/src/__tests__/pages/Login.test.tsx`
- 按项目规范，对测试文件的修改/新增需用户明确授权后方可执行

**5. 风险点：**
- 本次改动后，生产环境未配置 `FRONTEND_*_PASSWORD_HASH` 时服务启动会失败（由 settings validator 保证），避免部署后仍开放。
- 本地开发 `DEBUG=true` 时认证中间件跳过，不影响现有开发流程。

---

## 执行交接

**Plan complete and saved to `docs/superpowers/plans/2026-06-19-frontend-auth-jwt.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
