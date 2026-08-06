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


class PasswordChange(BaseModel):
    current: str = Field(min_length=1, max_length=200)
    replacement: str = Field(min_length=8, max_length=200)


class ProfileUpdate(BaseModel):
    displayName: str = Field("", max_length=80)


def _require_user(request: Request) -> dict:
    user = auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))
    if not user:
        raise HTTPException(status_code=401, detail="Entre para continuar")
    return user


@router.get("/users")
def list_users(request: Request) -> dict:
    """Names of everyone with an account, for labelling a shared library."""
    _require_user(request)
    return {"users": auth.list_users()}


@router.patch("/me")
def update_profile(payload: ProfileUpdate, request: Request) -> dict:
    user = _require_user(request)
    return {"user": auth.set_display_name(user["id"], payload.displayName)}


@router.post("/password", status_code=204)
def change_password(payload: PasswordChange, request: Request, response: Response) -> Response:
    """Change the password and sign every session out, including this one.

    Signing this one out too is the honest behaviour: if the change was made
    because somebody else had got in, a session left alive would defeat it, and
    there is no way to tell from here which session is which.
    """
    user = _require_user(request)
    try:
        auth.change_password(user["id"], payload.current, payload.replacement)
    except auth.AuthError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return Response(status_code=204)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return Response(status_code=204)
