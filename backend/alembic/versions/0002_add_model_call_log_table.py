"""Create model_call_logs table for persisting model usage counts.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = 'c853a95e4e86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "model_call_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("model_type", sa.String(20), nullable=False, index=True, comment="模型类型: yolo / llm / ocr / embedding"),
        sa.Column("model_config_id", sa.Integer(), nullable=True, comment="对应配置表的主键 ID, 可选"),
        sa.Column("ref_id", sa.Integer(), nullable=True, comment="关联的业务记录 ID, 可选"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("model_call_logs")
