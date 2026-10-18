"""add knowledge_entries (admin-entered Q&A knowledge base)

Revision ID: c4e8a1d7f203
Revises: b7d2f4a8c915
Create Date: 2026-10-18 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4e8a1d7f203'
down_revision: Union[str, Sequence[str], None] = 'b7d2f4a8c915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'knowledge_entries',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('question_key', sa.String(length=64), nullable=False),
        sa.Column('embedded_hash', sa.String(length=64), nullable=True),
        sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_entries_question_key'), 'knowledge_entries', ['question_key'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_knowledge_entries_question_key'), table_name='knowledge_entries')
    op.drop_table('knowledge_entries')
