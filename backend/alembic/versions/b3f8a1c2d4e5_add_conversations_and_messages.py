"""add_conversations_and_messages

Revision ID: b3f8a1c2d4e5
Revises: 775f6a43bd14
Create Date: 2026-05-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f8a1c2d4e5'
down_revision: Union[str, None] = '775f6a43bd14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # conversations 테이블 (active_leaf_id FK는 messages 생성 후 추가)
    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, server_default='새 대화'),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active_leaf_id', sa.Integer(), nullable=True),  # FK 나중에 추가
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    op.create_index('ix_conversations_project_id', 'conversations', ['project_id'])

    # messages 테이블
    op.create_table(
        'messages',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('conversation_id', sa.Integer(), sa.ForeignKey('conversations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('messages.id', ondelete='SET NULL'), nullable=True),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tokens_input', sa.Integer(), nullable=True),
        sa.Column('tokens_output', sa.Integer(), nullable=True),
        sa.Column('is_regenerated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_parent_id', 'messages', ['parent_id'])
    op.create_index('ix_messages_conversation_created', 'messages', ['conversation_id', 'created_at'])

    # conversations.active_leaf_id → messages.id FK (순환 참조이므로 나중에 추가)
    op.create_foreign_key(
        'fk_conversations_active_leaf_id',
        'conversations', 'messages',
        ['active_leaf_id'], ['id'],
        ondelete='SET NULL',
        use_alter=True,
    )


def downgrade() -> None:
    op.drop_constraint('fk_conversations_active_leaf_id', 'conversations', type_='foreignkey')
    op.drop_index('ix_messages_conversation_created', 'messages')
    op.drop_index('ix_messages_parent_id', 'messages')
    op.drop_index('ix_messages_conversation_id', 'messages')
    op.drop_table('messages')
    op.drop_index('ix_conversations_project_id', 'conversations')
    op.drop_index('ix_conversations_user_id', 'conversations')
    op.drop_table('conversations')
