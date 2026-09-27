"""Authentication API router endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth_service import auth_service

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new organization and administrator",
)
def register(
    data: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register a new organization, create its admin user, and return auth tokens."""
    _, access_token, refresh_token = auth_service.register(
        db=db,
        email=data.email,
        password=data.password,
        name=data.name,
        organization_name=data.organization_name,
    )
    set_refresh_cookie(response=response, refresh_token=refresh_token)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue tokens",
)
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Validate credentials, set the refresh token cookie, and return an access token."""
    _, access_token, refresh_token = auth_service.login(
        db=db,
        email=data.email,
        password=data.password,
    )
    set_refresh_cookie(response=response, refresh_token=refresh_token)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token and rotate refresh token cookie",
)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    x_requested_with: str | None = Header(None, alias="X-Requested-With"),
) -> TokenResponse:
    """Validate the refresh token cookie, rotate it, and return a new access token.

    Requires 'X-Requested-With: RicozPortfolio' header as CSRF mitigation.
    """
    if not x_requested_with or x_requested_with.strip() != "RicozPortfolio":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid X-Requested-With header.",
        )

    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token cookie missing.",
        )

    _, new_access_token, new_refresh_token = auth_service.refresh_tokens(
        db=db,
        refresh_token=refresh_token,
    )
    set_refresh_cookie(response=response, refresh_token=new_refresh_token)
    return TokenResponse(access_token=new_access_token, token_type="bearer")


@router.post(
    "/logout",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Log out and clear refresh token cookie",
)
def logout(response: Response) -> MessageResponse:
    """Clear the refresh token cookie."""
    clear_refresh_cookie(response)
    return MessageResponse(message="Successfully logged out.")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return profile and roles for the authenticated user."""
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        organization_id=current_user.organization_id,
        roles=[r.name for r in current_user.roles],
    )
