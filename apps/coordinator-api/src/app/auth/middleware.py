"""
Auth middleware for automatic route protection
"""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .jwt_auth import verify_access_token
from .security_matrix import AuthLevel, check_role_match, get_auth_level


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce auth requirements based on route security matrix

    This middleware automatically:
    1. Extracts Bearer token from Authorization header
    2. Verifies token validity
    3. Checks role requirements from security matrix
    4. Adds user info to request state
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Skip auth for public routes
        auth_level = get_auth_level(path)
        if auth_level == AuthLevel.NONE:
            return await call_next(request)

        # Extract token from Authorization header
        authorization = request.headers.get("Authorization")
        if not authorization:
            return Response(
                status_code=401,
                content='{"detail": "Authorization header required"}',
                media_type="application/json",
            )

        if not authorization.startswith("Bearer "):
            return Response(
                status_code=401,
                content='{"detail": "Invalid authorization header format"}',
                media_type="application/json",
            )

        token = authorization[7:]

        try:
            # Verify token
            payload = verify_access_token(token)

            # Check role if required
            user_role = payload.get("role")
            if not check_role_match(auth_level, user_role):
                required_role = auth_level.value
                return Response(
                    status_code=403,
                    content=f'{{"detail": "Role \'{required_role}\' required"}}',
                    media_type="application/json",
                )

            # Add user info to request state
            request.state.user = payload
            request.state.user_id = payload.get("sub")
            request.state.user_role = user_role

        except Exception as e:
            return Response(
                status_code=401,
                content=f'{{"detail": "Invalid token: {str(e)}"}}',
                media_type="application/json",
            )

        return await call_next(request)
