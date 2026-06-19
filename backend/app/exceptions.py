"""Custom exception hierarchy for the application."""


class AppException(Exception):
    """Base application exception with code and HTTP status."""

    def __init__(self, message: str, code: int = 1, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found (HTTP 404)."""

    def __init__(self, message: str = "资源不存在", code: int = 404):
        super().__init__(message, code=code, status_code=404)


class ValidationException(AppException):
    """Request validation error (HTTP 422)."""

    def __init__(self, message: str = "参数验证失败", code: int = 422):
        super().__init__(message, code=code, status_code=422)


class AuthException(AppException):
    """Authentication / authorization error (HTTP 401)."""

    def __init__(self, message: str = "认证失败", code: int = 401):
        super().__init__(message, code=code, status_code=401)


class BusinessException(AppException):
    """Business logic error (HTTP 400)."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message, code=code, status_code=400)


class ServiceUnavailableException(AppException):
    """External service unavailable (HTTP 503)."""

    def __init__(self, message: str = "服务暂不可用", code: int = 503):
        super().__init__(message, code=code, status_code=503)
