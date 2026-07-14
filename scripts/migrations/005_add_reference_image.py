def upgrade(db):
    db._conn.execute("ALTER TABLE users ADD COLUMN reference_image_path TEXT")
    db._conn.commit()


def downgrade(db):
    # SQLite does not support DROP COLUMN easily in all versions; for safety we leave the column.
    # If a full drop is required in future, recreate table or use a more complex migration.
    pass
