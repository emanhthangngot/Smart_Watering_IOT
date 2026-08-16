"""Reusable FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header, HTTPException, status

from .auth import AuthenticationError, OperatorIdentity, authenticate_operator


def require_operator(x_operator_token: str | None = Header(default=None)) -> OperatorIdentity:
    try:
        return authenticate_operator(x_operator_token)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
