import os
import uuid

import psycopg
import redis


def test_postgres_persists_request_record():
    database_url = os.environ["DATABASE_URL"]
    api_key = "ci-test-" + uuid.uuid4().hex

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO requests (api_key, resource, status, algorithm)
                VALUES (%s, %s, %s, %s)
                RETURNING api_key, resource, status, algorithm
                """,
                (api_key, "ci-integration-test", 200, "sliding"),
            )
            row = cur.fetchone()

        assert row == (api_key, "ci-integration-test", 200, "sliding")

        with conn.cursor() as cur:
            cur.execute("DELETE FROM requests WHERE api_key = %s", (api_key,))


def test_redis_can_store_and_retrieve_values():
    client = redis.Redis.from_url(os.environ["REDIS_URL"])
    key = "ci-integration-test:" + uuid.uuid4().hex

    try:
        assert client.set(key, "working", ex=30)
        assert client.get(key) == b"working"
    finally:
        client.delete(key)
        client.close()
