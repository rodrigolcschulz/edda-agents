import psycopg
from langgraph.checkpoint.postgres import PostgresSaver


class PostgresCheckpointer:
    def __init__(self, database_url: str) -> None:
        self._connection = psycopg.connect(database_url, autocommit=True, prepare_threshold=0)
        self.saver = PostgresSaver(self._connection)

    def setup(self) -> None:
        self.saver.setup()

    def close(self) -> None:
        self._connection.close()