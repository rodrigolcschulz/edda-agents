from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.models.workflow import Artifact


class ArtifactStore:
    def __init__(
        self,
        database_url: str | None = None,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        bucket: str = "edda-artifacts",
        region: str = "us-east-1",
        s3_client: Any | None = None,
    ) -> None:
        self._connection = psycopg.connect(database_url, autocommit=True) if database_url else None
        self._bucket = bucket
        self._s3 = s3_client
        self._bucket_ready = False
        self._metadata: dict[str, dict[str, Any]] = {}
        self._links: set[tuple[str, str, str]] = set()

        if self._s3 is None and endpoint_url:
            import boto3
            from botocore.config import Config

            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=Config(s3={"addressing_style": "path"}),
            )

    def setup(self) -> None:
        if not self._connection:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS artifacts (
                    id uuid PRIMARY KEY,
                    kind text NOT NULL,
                    bucket text NOT NULL,
                    object_key text NOT NULL UNIQUE,
                    filename text,
                    content_type text NOT NULL,
                    size_bytes bigint NOT NULL,
                    sha256 text NOT NULL,
                    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now()
                );

                CREATE TABLE IF NOT EXISTS workflow_run_artifacts (
                    workflow_run_id uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    artifact_id uuid NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
                    role text NOT NULL CHECK (role IN ('input', 'output')),
                    created_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (workflow_run_id, artifact_id, role)
                );

                CREATE INDEX IF NOT EXISTS workflow_run_artifacts_artifact_idx
                ON workflow_run_artifacts (artifact_id);
                """
            )

    def store_file(
        self,
        path: str | Path,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_s3()
        file_path = Path(path)
        artifact_id = str(uuid4())
        safe_filename = filename.replace("\\", "/").rsplit("/", 1)[-1] or "upload"
        object_key = f"uploads/{artifact_id}/{safe_filename}"
        checksum = sha256()
        size_bytes = 0
        with file_path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                size_bytes += len(chunk)
                checksum.update(chunk)
        with file_path.open("rb") as source:
            self._s3.upload_fileobj(
                source,
                self._bucket,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )

        record = {
            "id": artifact_id,
            "kind": "input_file",
            "bucket": self._bucket,
            "object_key": object_key,
            "filename": safe_filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "sha256": checksum.hexdigest(),
            "metadata": metadata or {},
        }
        self._save_metadata(record)
        return record

    def store_content(self, artifact: Artifact, workflow_run_id: str) -> Artifact:
        self._require_s3()
        payload = json.dumps(artifact.content, ensure_ascii=False, default=str).encode("utf-8")
        object_key = f"runs/{workflow_run_id}/artifacts/{artifact.id}.json"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=payload,
            ContentType="application/json",
        )
        record = {
            "id": artifact.id,
            "kind": artifact.type,
            "bucket": self._bucket,
            "object_key": object_key,
            "filename": None,
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": sha256(payload).hexdigest(),
            "metadata": {"source_node_id": artifact.source_node_id},
        }
        self._save_metadata(record)
        self.link_to_run(workflow_run_id, artifact.id, "output")
        return artifact.model_copy(
            update={key: record[key] for key in ("bucket", "object_key", "content_type", "size_bytes", "sha256")}
        )

    def link_to_run(self, workflow_run_id: str, artifact_id: str, role: str) -> None:
        if role not in {"input", "output"}:
            raise ValueError("Artifact role must be 'input' or 'output'.")
        if self._connection:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO workflow_run_artifacts (workflow_run_id, artifact_id, role)
                    VALUES (%s::uuid, %s::uuid, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (workflow_run_id, artifact_id, role),
                )
            return
        self._links.add((workflow_run_id, artifact_id, role))

    def get_metadata(self, artifact_id: str) -> dict[str, Any] | None:
        if self._connection:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id::text, kind, bucket, object_key, filename, content_type,
                           size_bytes, sha256, metadata
                    FROM artifacts WHERE id = %s::uuid
                    """,
                    (artifact_id,),
                )
                row = cursor.fetchone()
            if row is None:
                return None
            keys = ("id", "kind", "bucket", "object_key", "filename", "content_type", "size_bytes", "sha256", "metadata")
            return dict(zip(keys, row, strict=True))
        return self._metadata.get(artifact_id)

    def _save_metadata(self, record: dict[str, Any]) -> None:
        if self._connection:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO artifacts (
                        id, kind, bucket, object_key, filename, content_type,
                        size_bytes, sha256, metadata
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        kind = EXCLUDED.kind,
                        bucket = EXCLUDED.bucket,
                        object_key = EXCLUDED.object_key,
                        filename = EXCLUDED.filename,
                        content_type = EXCLUDED.content_type,
                        size_bytes = EXCLUDED.size_bytes,
                        sha256 = EXCLUDED.sha256,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        record["id"],
                        record["kind"],
                        record["bucket"],
                        record["object_key"],
                        record["filename"],
                        record["content_type"],
                        record["size_bytes"],
                        record["sha256"],
                        Jsonb(record["metadata"]),
                    ),
                )
            return
        self._metadata[record["id"]] = record

    def _require_s3(self) -> None:
        if self._s3 is None:
            raise RuntimeError("Artifact object storage is not configured.")
        if not self._bucket_ready:
            try:
                self._s3.head_bucket(Bucket=self._bucket)
            except Exception:
                self._s3.create_bucket(Bucket=self._bucket)
            self._bucket_ready = True

    def close(self) -> None:
        if self._connection:
            self._connection.close()