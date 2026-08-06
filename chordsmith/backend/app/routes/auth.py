"""Account endpoints: register, sign in, sign out, who am I."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth
from ..config import SESSION_DAYS

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=200)
    displayName: str = Field("", max_length=80)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,  # unreadable from JavaScript, so an XSS cannot lift it
        samesite="lax",  # the app is same-origin; lax still allows normal navigation
        path="/",
    )


@router.get("/me")
def me(request: Request) -> dict:
    """Who is signed in, and whether signing in is required at all."""
    user = auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))
    return {
        "user": user,
        "required": auth.enabled(),
        "hasUsers": auth.count_users() > 0,
    }


@router.post("/register", status_code=201)
def register(credentials: Credentials, response: Response) -> dict:
    try:
        user = auth.create_user(
            credentials.username, credentials.password, credentials.displayName
        )
    except auth.AuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    _set_cookie(response, auth.start_session(user["id"]))
    return {"user": user}


@router.post("/login")
def login(credentials: Credentials, response: Response) -> dict:
    try:
        user = auth.authenticate(credentials.username, credentials.password)
    except auth.AuthError as error:
        # 401 rather than 400: this is a failed credential, not a malformed
        # request, and the client should offer the form again.
        raise HTTPException(status_code=401, detail=str(error)) from error

    _set_cookie(response, auth.start_session(user["id"]))
    return {"user": user}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return Response(status_code=204)
