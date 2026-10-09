"""Service layer for Project and ProjectMember operations (Phase 7)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.project import Project, ProjectStatus
from app.models.project_member import ProjectMemberRole
from app.models.user import User
from app.repositories.portfolio_repository import portfolio_repository
from app.repositories.project_member_repository import project_member_repository
from app.repositories.project_repository import project_repository
from app.repositories.user_repository import user_repository
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectMemberCreateRequest,
    ProjectMemberResponse,
    ProjectMemberRoleEnum,
    ProjectMemberUpdateRequest,
    ProjectUpdateRequest,
)


def _get_caller_role_names(caller: User) -> set[str]:
    """Return the set of org-level role names held by the caller."""
    return {r.name for r in caller.roles}


def _caller_is_broad_manager(caller: User) -> bool:
    """Return True if caller is org_admin or portfolio_manager."""
    roles = _get_caller_role_names(caller)
    return bool(roles & {"org_admin", "portfolio_manager"})


def _validate_portfolio_in_org(
    db: Session,
    portfolio_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> None:
    """Raise 404 if portfolio_id does not belong to the org or is soft-deleted."""
    portfolio = portfolio_repository.get_by_id_within_org(
        db, portfolio_id=portfolio_id, organization_id=organization_id
    )
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found in your organization.",
        )


def _require_project_in_org(
    db: Session,
    project_id: uuid.UUID,
    organization_id: uuid.UUID,
) -> Project:
    """Return active project or raise 404."""
    project = project_repository.get_by_id_within_org(
        db, project_id=project_id, organization_id=organization_id
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return project


def _build_member_response(member, user: User) -> ProjectMemberResponse:
    """Build a ProjectMemberResponse from a ProjectMember + User pair."""
    return ProjectMemberResponse(
        id=member.id,
        project_id=member.project_id,
        user_id=member.user_id,
        user_name=user.name,
        user_email=user.email,
        project_role=ProjectMemberRoleEnum(member.project_role.value),
        created_at=member.created_at,
    )


class ProjectService:
    """Orchestrates business logic and permissions for projects and their members."""

    # ------------------------------------------------------------------
    # Project CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def create_project(
        db: Session,
        caller: User,
        payload: ProjectCreateRequest,
    ) -> Project:
        """Create a new direct project.

        Role: portfolio_manager or org_admin (enforced at router level).
        Initial status: always 'planned' regardless of any client input.
        Atomically creates the project AND assigns the creator as project manager.
        If either write fails, both are rolled back.
        """
        # Validate target portfolio if supplied
        if payload.portfolio_id is not None:
            _validate_portfolio_in_org(db, payload.portfolio_id, caller.organization_id)

        try:
            # Create project
            project = project_repository.create(
                db,
                organization_id=caller.organization_id,
                name=payload.name,
                description=payload.description,
                portfolio_id=payload.portfolio_id,
                status=ProjectStatus.planned,
            )

            # Atomically create creator membership as project manager
            project_member_repository.create_member(
                db,
                project_id=project.id,
                user_id=caller.id,
                project_role=ProjectMemberRole.manager,
            )

            db.commit()
            db.refresh(project)
            return project
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def list_projects(
        db: Session,
        caller: User,
        portfolio_id: uuid.UUID | None,
        filter_status: ProjectStatus | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Project], int]:
        """List projects with dual-tier visibility.

        org_admin / portfolio_manager → all projects in org.
        project_manager / team_member → only projects they are a member of.

        If portfolio_id filter is provided, validates it exists and is active.
        """
        # Validate portfolio filter
        if portfolio_id is not None:
            _validate_portfolio_in_org(db, portfolio_id, caller.organization_id)

        if _caller_is_broad_manager(caller):
            return project_repository.list_all_within_org(
                db,
                organization_id=caller.organization_id,
                portfolio_id=portfolio_id,
                status=filter_status,
                limit=limit,
                offset=offset,
            )
        return project_repository.list_user_member_projects(
            db,
            organization_id=caller.organization_id,
            user_id=caller.id,
            portfolio_id=portfolio_id,
            status=filter_status,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    def get_project(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> tuple[Project, list[ProjectMemberResponse]]:
        """Retrieve project details with its member list.

        org_admin / portfolio_manager: always authorized.
        project_manager / team_member: must be a project member (any role); else 403.
        """
        project = _require_project_in_org(db, project_id, caller.organization_id)

        if not _caller_is_broad_manager(caller):
            membership = project_member_repository.get_membership(
                db, project_id=project_id, user_id=caller.id
            )
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You are not a member of this project.",
                )

        pairs = project_member_repository.list_by_project(db, project_id=project_id)
        members = [_build_member_response(m, u) for m, u in pairs]
        return project, members

    @staticmethod
    def update_project(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: ProjectUpdateRequest,
    ) -> Project:
        """Update project attributes.

        Permissions:
        - org_admin / portfolio_manager: always authorized.
        - project_manager / team_member: must be a project member with project_role='manager';
          else 403.

        PATCH semantics for portfolio_id (via model_fields_set):
        - omitted       → preserve existing portfolio_id
        - explicit null → clear portfolio_id (set to None)
        - valid UUID    → must belong to org and be active; reassign
        """
        project = _require_project_in_org(db, project_id, caller.organization_id)

        if not _caller_is_broad_manager(caller):
            membership = project_member_repository.get_membership(
                db, project_id=project_id, user_id=caller.id
            )
            if not membership or membership.project_role != ProjectMemberRole.manager:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You must be a project manager to update this project.",
                )

        # Resolve status
        new_status: ProjectStatus | None = None
        if payload.status is not None:
            new_status = ProjectStatus(payload.status.value)

        # Resolve portfolio_id changes
        clear_portfolio = False
        new_portfolio_id: uuid.UUID | None = None
        if "portfolio_id" in payload.model_fields_set:
            if payload.portfolio_id is None:
                clear_portfolio = True
            else:
                _validate_portfolio_in_org(db, payload.portfolio_id, caller.organization_id)
                new_portfolio_id = payload.portfolio_id

        project_repository.update(
            db,
            project=project,
            name=payload.name,
            description=payload.description,
            status=new_status,
            portfolio_id=new_portfolio_id,
            clear_portfolio=clear_portfolio,
        )
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def delete_project(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> None:
        """Soft-delete a project.

        Role: portfolio_manager or org_admin only (enforced at router level).
        project_manager / team_member cannot delete projects even if assigned as manager.
        """
        project = _require_project_in_org(db, project_id, caller.organization_id)
        project_repository.soft_delete(db, project)
        db.commit()

    # ------------------------------------------------------------------
    # Member operations
    # ------------------------------------------------------------------

    @staticmethod
    def _require_project_manager_authz(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> None:
        """Raise 403 unless caller is org_admin, portfolio_manager, or assigned project manager."""
        if _caller_is_broad_manager(caller):
            return
        membership = project_member_repository.get_membership(
            db, project_id=project_id, user_id=caller.id
        )
        if not membership or membership.project_role != ProjectMemberRole.manager:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions to manage project members.",
            )

    @staticmethod
    def add_member(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        payload: ProjectMemberCreateRequest,
    ) -> ProjectMemberResponse:
        """Add a user to a project.

        Authz: org_admin, portfolio_manager, or assigned project manager.
        Validates target user belongs to the same org and is active.
        Returns 409 if the user is already a member.
        """
        # Validate project exists
        _require_project_in_org(db, project_id, caller.organization_id)

        # Authorization
        ProjectService._require_project_manager_authz(db, caller, project_id)

        # Validate target user is in the same org and active
        target_user = user_repository.get_by_id_within_org(
            db, user_id=payload.user_id, organization_id=caller.organization_id
        )
        if not target_user or not target_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in your organization.",
            )

        # Check for duplicate membership
        existing = project_member_repository.get_membership(
            db, project_id=project_id, user_id=payload.user_id
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User is already a member of this project.",
            )

        member = project_member_repository.create_member(
            db,
            project_id=project_id,
            user_id=payload.user_id,
            project_role=ProjectMemberRole(payload.project_role.value),
        )
        db.commit()
        db.refresh(member)
        return _build_member_response(member, target_user)

    @staticmethod
    def list_members(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
    ) -> list[ProjectMemberResponse]:
        """List members of a project.

        Authz: org_admin, portfolio_manager, or any assigned project member.
        """
        _require_project_in_org(db, project_id, caller.organization_id)

        if not _caller_is_broad_manager(caller):
            membership = project_member_repository.get_membership(
                db, project_id=project_id, user_id=caller.id
            )
            if not membership:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Forbidden: You are not a member of this project.",
                )

        pairs = project_member_repository.list_by_project(db, project_id=project_id)
        return [_build_member_response(m, u) for m, u in pairs]

    @staticmethod
    def update_member_role(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        target_user_id: uuid.UUID,
        payload: ProjectMemberUpdateRequest,
    ) -> ProjectMemberResponse:
        """Update a project member's role.

        Authz: org_admin, portfolio_manager, or assigned project manager.
        Acquires SELECT FOR UPDATE on the project row to serialize concurrent
        last-manager demotions.
        Returns 400 if the operation would leave the project with 0 managers.
        """
        # Row lock to serialize concurrent manager operations
        locked_project = project_repository.get_by_id_within_org_locked(
            db, project_id=project_id, organization_id=caller.organization_id
        )
        if not locked_project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        # Authorization
        ProjectService._require_project_manager_authz(db, caller, project_id)

        member = project_member_repository.get_membership(
            db, project_id=project_id, user_id=target_user_id
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project member not found.",
            )

        new_role = ProjectMemberRole(payload.project_role.value)

        # Last-manager guard: if demoting manager → member, ensure at least one remains
        if (
            member.project_role == ProjectMemberRole.manager
            and new_role == ProjectMemberRole.member
        ):
            manager_count = project_member_repository.count_project_managers(
                db, project_id=project_id
            )
            if manager_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove or demote the last project manager from the project.",
                )

        updated = project_member_repository.update_role(db, member=member, project_role=new_role)

        # Retrieve user details for response
        target_user = user_repository.get_by_id(db, user_id=target_user_id)
        db.commit()
        db.refresh(updated)
        return _build_member_response(updated, target_user)  # type: ignore[arg-type]

    @staticmethod
    def remove_member(
        db: Session,
        caller: User,
        project_id: uuid.UUID,
        target_user_id: uuid.UUID,
    ) -> None:
        """Remove a member from a project.

        Authz: org_admin, portfolio_manager, or assigned project manager.
        Acquires SELECT FOR UPDATE on the project row to serialize concurrent
        last-manager removal attempts.
        Returns 400 if the operation would leave the project with 0 managers.
        """
        # Row lock to serialize concurrent manager operations
        locked_project = project_repository.get_by_id_within_org_locked(
            db, project_id=project_id, organization_id=caller.organization_id
        )
        if not locked_project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found.",
            )

        # Authorization
        ProjectService._require_project_manager_authz(db, caller, project_id)

        member = project_member_repository.get_membership(
            db, project_id=project_id, user_id=target_user_id
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project member not found.",
            )

        # Last-manager guard
        if member.project_role == ProjectMemberRole.manager:
            manager_count = project_member_repository.count_project_managers(
                db, project_id=project_id
            )
            if manager_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove the last project manager from the project.",
                )

        project_member_repository.delete_member(db, member)
        db.commit()


project_service = ProjectService()
