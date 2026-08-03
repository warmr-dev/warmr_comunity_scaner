"""Initial schema placeholder — MVP uses Base.metadata.create_all via init-db.

Generate a real revision later:
  alembic revision --autogenerate -m "init"
"""

from alembic import op  # noqa: F401


def upgrade() -> None:
    # Intentionally empty for bootstrap; use `community-scanner init-db`.
    pass


def downgrade() -> None:
    pass
