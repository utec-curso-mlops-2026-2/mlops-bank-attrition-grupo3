"""Acceso a datos en S3 (o local) con trazabilidad: SHA-256 y VersionId de cada archivo.

Las rutas de config.yaml admiten variables de entorno, p. ej. s3://${MLOPS_DATA_BUCKET}/raw/202611.
Los datos crudos se versionan por fecha de corte: s3://<bucket>/raw/<yyyymm>/<archivo>.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

_UNRESOLVED = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def resolve(uri) -> str:
    """Expandir variables de entorno y fallar si alguna no está definida."""
    expanded = os.path.expandvars(str(uri))
    missing = _UNRESOLVED.findall(expanded)
    if missing:
        raise ValueError(f"Variables de entorno sin definir en la ruta {uri!r}: {missing}")
    return expanded


def is_s3(uri: str) -> bool:
    return str(uri).startswith("s3://")


def join(base, *parts) -> str:
    base = resolve(base)
    if is_s3(base):
        return "/".join([base.rstrip("/"), *(str(p).strip("/") for p in parts)])
    return str(Path(base, *map(str, parts)))


def split_s3(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    key = parsed.path.lstrip("/")
    if parsed.scheme != "s3" or not parsed.netloc or not key:
        raise ValueError(f"URI S3 inválida, se espera s3://bucket/clave: {uri!r}")
    return parsed.netloc, key


def s3_client(client=None):
    if client is not None:
        return client
    import boto3

    return boto3.client("s3")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_bytes(uri, version_id=None, client=None) -> tuple[bytes, dict]:
    """Leer un archivo y devolver (contenido, procedencia)."""
    uri = resolve(uri)
    if is_s3(uri):
        bucket, key = split_s3(uri)
        extra = {"VersionId": version_id} if version_id else {}
        response = s3_client(client).get_object(Bucket=bucket, Key=key, **extra)
        with response["Body"] as body:
            payload = body.read()
        version = response.get("VersionId")
    else:
        payload, version = Path(uri).read_bytes(), None
    return payload, {"uri": uri, "version_id": version, "sha256": sha256(payload),
                     "bytes": len(payload)}


def write_bytes(uri, payload: bytes, client=None) -> dict:
    uri = resolve(uri)
    digest = sha256(payload)
    if is_s3(uri):
        bucket, key = split_s3(uri)
        response = s3_client(client).put_object(
            Bucket=bucket, Key=key, Body=payload, Metadata={"sha256": digest},
            ChecksumSHA256=base64.b64encode(hashlib.sha256(payload).digest()).decode(),
        )
        version = response.get("VersionId")
    else:
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
        Path(uri).write_bytes(payload)
        version = None
    return {"uri": uri, "version_id": version, "sha256": digest, "bytes": len(payload)}


def read_csv(uri, version_id=None, client=None, **kwargs) -> tuple[pd.DataFrame, dict]:
    payload, info = read_bytes(uri, version_id, client)
    df = pd.read_csv(io.BytesIO(payload), **kwargs)
    return df, {**info, "rows": len(df)}


def read_parquet(uri, version_id=None, client=None) -> tuple[pd.DataFrame, dict]:
    payload, info = read_bytes(uri, version_id, client)
    df = pd.read_parquet(io.BytesIO(payload))
    return df, {**info, "rows": len(df)}


def write_parquet(df: pd.DataFrame, uri, client=None) -> dict:
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    return {**write_bytes(uri, buffer.getvalue(), client), "rows": len(df)}


def write_csv(df: pd.DataFrame, uri, client=None) -> dict:
    payload = df.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return {**write_bytes(uri, payload, client), "rows": len(df)}


def read_json(uri, client=None) -> dict:
    return json.loads(read_bytes(uri, client=client)[0])


def write_json(value: dict, uri, client=None) -> dict:
    payload = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    return write_bytes(uri, payload, client)


def check_against_manifest(info: dict, filename: str, manifest: dict | None) -> None:
    """Exigir que el archivo leído sea exactamente el registrado en el manifiesto."""
    if not manifest:
        return
    entry = next((f for f in manifest.get("files", []) if f["filename"] == filename), None)
    if entry and entry.get("sha256") and entry["sha256"] != info["sha256"]:
        raise ValueError(
            f"{filename}: el SHA-256 leído ({info['sha256'][:12]}…) no coincide con el "
            f"manifiesto ({entry['sha256'][:12]}…). Registre una nueva versión de datos."
        )


def _existing(client, bucket: str, key: str):
    from botocore.exceptions import ClientError

    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise


def upload_raw(origin, destination, manifest_path, client=None) -> dict:
    """Subir los archivos del manifiesto a destination sin sobrescribir otra versión.

    Exige que estén todos los archivos del manifiesto y que el bucket tenga versionado activo.
    Comprueba el SHA-256 local contra el manifiesto, es idempotente si el objeto ya existe
    con el mismo contenido y actualiza el manifiesto con la URI y el VersionId de S3.
    """
    destination = resolve(destination)
    if not is_s3(destination):
        raise ValueError(f"El destino debe ser s3://…; se recibió {destination!r}")
    client = s3_client(client)
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    release = manifest.get("dataset_release")
    if release and not destination.rstrip("/").endswith(f"/{release}"):
        raise ValueError(f"El destino debe terminar en /{release} (dataset_release del manifiesto).")

    # Una entrega se sube completa: los CSV y el diccionario.
    pending = [entry for entry in manifest["files"] if (Path(origin) / entry["filename"]).exists()]
    missing = [e["filename"] for e in manifest["files"] if e not in pending]
    if missing:
        raise FileNotFoundError(f"Faltan archivos de datos en {origin}: {missing}")

    # Validar todo antes de la primera escritura, empezando por el versionado del bucket.
    bucket = split_s3(join(destination, "_"))[0]
    versioning = client.get_bucket_versioning(Bucket=bucket).get("Status")
    if versioning != "Enabled":
        raise ValueError(f"El bucket {bucket} no tiene versionado activo ({versioning}); no se subió nada.")
    plan = []
    for entry in pending:
        payload = (Path(origin) / entry["filename"]).read_bytes()
        digest = sha256(payload)
        if entry.get("sha256") and entry["sha256"] != digest:
            raise ValueError(f"{entry['filename']}: el archivo local no coincide con el manifiesto.")
        if "row_count" in entry:
            rows = len(pd.read_csv(io.BytesIO(payload), usecols=[0]))
            if rows != entry["row_count"]:
                raise ValueError(f"{entry['filename']}: {rows} filas; manifiesto: {entry['row_count']}.")
        bucket, key = split_s3(join(destination, entry["filename"]))
        head = _existing(client, bucket, key)
        if head is not None and head.get("Metadata", {}).get("sha256") != digest:
            raise ValueError(
                f"s3://{bucket}/{key} ya existe con otro contenido. Los datos de una versión "
                "son inmutables: use una nueva carpeta raw/<yyyymm>/."
            )
        plan.append((entry, payload, digest, head))

    results = []
    for entry, payload, digest, head in plan:
        uri = join(destination, entry["filename"])
        if head is not None:
            info, action = {"uri": uri, "version_id": head.get("VersionId")}, "sin cambios"
        else:
            info, action = write_bytes(uri, payload, client), "subido"
        if not info["version_id"]:
            raise RuntimeError(f"{uri} no tiene VersionId: active el versionado del bucket.")
        entry.update(source_uri=uri, version_id=info["version_id"], sha256=digest,
                     status="registrado")
        results.append({"archivo": entry["filename"], "accion": action,
                        "version_id": info["version_id"]})

    now = datetime.now(timezone.utc).isoformat()
    manifest.update(status="registrado", source_system="s3", recorded_at_utc=now)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    return {"destino": destination, "archivos": results, "manifiesto": str(manifest_path)}


def main() -> None:
    from dotenv import load_dotenv

    from bank_attrition.features import load_config

    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__)
    commands = ap.add_subparsers(dest="command", required=True)
    upload = commands.add_parser("subir", help="Subir los datos crudos a raw_path en S3.")
    upload.add_argument("--origen", required=True, help="Carpeta local con los CSV de Kaggle.")
    upload.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)["data"]
    print(json.dumps(upload_raw(args.origen, cfg["raw_path"], cfg["manifest"]), indent=2,
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
