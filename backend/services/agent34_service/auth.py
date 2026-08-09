import hmac

from fastapi import Header, HTTPException, Request, status


def require_bearer(request: Request, authorization: str | None = Header(default=None)) -> None:
    expected = request.app.state.settings.shared_token
    prefix = "Bearer "
    if not expected or not authorization or not authorization.startswith(prefix):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
    supplied = authorization[len(prefix):]
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token")
