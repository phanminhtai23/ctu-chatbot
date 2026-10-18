"""add conversation shares

Revision ID: d4e9b2a7c611
Revises: c3d8a1f50b72
Create Date: 2026-10-18 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e9b2a7c611'
down_revision: Union[str, Sequence[str], None] = 'c3d8a1f50b72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('conversation_shares',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=5), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('token', sa.String(length=64), nullable=True),
    sa.Column('permission', sa.String(length=5), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('email', 'link')", name='ck_conversation_shares_kind'),
    sa.CheckConstraint("permission IN ('view', 'chat')", name='ck_conversation_shares_permission'),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('conversation_id', 'email', name='uq_conversation_shares_conversation_email')
    )
    op.create_index(op.f('ix_conversation_shares_conversation_id'), 'conversation_shares', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_conversation_shares_email'), 'conversation_shares', ['email'], unique=False)
    op.create_index(op.f('ix_conversation_shares_token'), 'conversation_shares', ['token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_conversation_shares_token'), table_name='conversation_shares')
    op.drop_index(op.f('ix_conversation_shares_email'), table_name='conversation_shares')
    op.drop_index(op.f('ix_conversation_shares_conversation_id'), table_name='conversation_shares')
    op.drop_table('conversation_shares')
