"""Domain errors and exit codes."""

from __future__ import annotations


class ExitCode:
    SUCCESS = 0
    USAGE = 2
    BLOCKED = 3
    STAGE = 4
    STATE = 5
    INTERNAL = 70
    INTERRUPTED = 130


class AppError(Exception):
    """Base application error with stable machine code."""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        exit_code: int = ExitCode.STAGE,
        next_step: str | None = None,
        retryable: bool = False,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.next_step = next_step
        self.retryable = retryable
        self.__cause__ = cause


class UsageError(AppError):
    def __init__(self, message: str, *, code: str = "usage_error", next_step: str | None = None):
        super().__init__(message, code=code, exit_code=ExitCode.USAGE, next_step=next_step)


class BlockedError(AppError):
    def __init__(self, message: str, *, code: str = "blocked", next_step: str | None = None):
        super().__init__(message, code=code, exit_code=ExitCode.BLOCKED, next_step=next_step)


class StateError(AppError):
    def __init__(self, message: str, *, code: str = "state_corrupt", next_step: str | None = None):
        super().__init__(message, code=code, exit_code=ExitCode.STATE, next_step=next_step)
