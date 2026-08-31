class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class NotFoundError(DomainError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__("NOT_FOUND", message, 404)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "无权访问该资源"):
        super().__init__("FORBIDDEN", message, 403)


class ConflictError(DomainError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 409)


class ValidationError(DomainError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 422)
