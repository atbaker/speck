"""Message full text search (FTS)

Revision ID: fb0b0b872034
Revises: a36d1b2d48ba
Create Date: 2024-10-10 18:49:09.486762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fb0b0b872034'
down_revision: Union[str, None] = 'a36d1b2d48ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the FTS5 virtual table using the content option
    op.execute("""
        CREATE VIRTUAL TABLE messages_fts USING fts5(
            body, 
            subject,
            content='messages',
            content_rowid='rowid',
            tokenize='porter'
        )
    """)

    # Add triggers to keep the FTS table in sync with the messages table
    # Create triggers to sync the messages and the FTS table
    op.execute("""
        CREATE TRIGGER message_after_insert AFTER INSERT ON messages BEGIN
            INSERT INTO messages_fts(rowid, body, subject) VALUES (new.rowid, new.body, new.subject);
        END;
    """)
    op.execute("""
        CREATE TRIGGER message_after_delete AFTER DELETE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, body, subject) VALUES('delete', old.rowid, old.body, old.subject);
        END;
    """)
    op.execute("""
        CREATE TRIGGER message_after_update AFTER UPDATE ON messages BEGIN
            INSERT INTO messages_fts(messages_fts, rowid, body, subject) VALUES('delete', old.rowid, old.body, old.subject);
            INSERT INTO messages_fts(rowid, body, subject) VALUES (new.rowid, new.body, new.subject);
        END;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS message_after_insert")
    op.execute("DROP TRIGGER IF EXISTS message_after_delete")
    op.execute("DROP TRIGGER IF EXISTS message_after_update")
    op.drop_table('messages_fts', if_exists=True)
