"""add_projects_table_and_project_id_to_code_files

Revision ID: a26cfec84c6d
Revises: cc57c89021a4
Create Date: 2026-05-17 23:16:17.686608

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a26cfec84c6d'
down_revision: Union[str, None] = 'cc57c89021a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)

    op.add_column("code_files", sa.Column("project_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_code_files_project_id", "code_files", "projects", ["project_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_code_files_project_id"), "code_files", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_code_files_project_id"), table_name="code_files")
    op.drop_constraint("fk_code_files_project_id", "code_files", type_="foreignkey")
    op.drop_column("code_files", "project_id")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")
