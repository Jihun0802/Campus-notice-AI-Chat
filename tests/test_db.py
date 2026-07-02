import tempfile
import unittest
from pathlib import Path

from campus_notice_ai.db import connect, init_db, split_sql_statements


class DbTests(unittest.TestCase):
    def test_split_sql_statements_keeps_semicolon_inside_quotes(self):
        statements = split_sql_statements(
            "CREATE TABLE example (value TEXT DEFAULT ';');"
            "INSERT INTO example (value) VALUES ('a; b');"
        )

        self.assertEqual(len(statements), 2)
        self.assertIn("DEFAULT ';'", statements[0])
        self.assertIn("'a; b'", statements[1])

    def test_init_db_can_be_called_more_than_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.sqlite3"
            with connect(db_path) as conn:
                init_db(conn)
            with connect(db_path) as conn:
                init_db(conn)
                versions = [
                    row["version"]
                    for row in conn.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    ).fetchall()
                ]

        self.assertIn("001_notice_rag_foundation", versions)
        self.assertIn("002_ingestion_quality", versions)
        self.assertIn("003_notice_media_pipeline", versions)
        self.assertIn("004_real_data_validation", versions)


if __name__ == "__main__":
    unittest.main()
