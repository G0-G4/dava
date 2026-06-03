def upgrade(db):
    db._create_tables()


def downgrade(db):
    db._conn.execute("DROP TABLE IF EXISTS global_config")
    db._conn.execute("DROP TABLE IF EXISTS user_config")
    db._conn.execute("DROP TABLE IF EXISTS users")
    db._conn.commit()