"""add user_files (files stored on Cloudinary)

Revision ID: b7d2f4a8c915
Revises: a1c7e4d9b3f6
Create Date: 2026-10-18 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a8c915'
down_revision: Union[str, Sequence[str], None] = 'a1c7e4d9b3f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_files',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('filename', sa.String(length=200), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('public_id', sa.String(length=300), nullable=False),
        sa.Column('resource_type', sa.String(length=10), nullable=False),
        sa.Column('delivery_type', sa.String(length=15), nullable=False),
        sa.Column('url', sa.String(length=600), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("kind IN ('avatar', 'attachment')", name='ck_user_files_kind'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_files_user_id'), 'user_files', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_files_user_id'), table_name='user_files')
    op.drop_table('user_files')
