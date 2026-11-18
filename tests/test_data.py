import io
import json

import pandas as pd
import pytest
import yaml
from botocore.exceptions import ClientError

from bank_attrition import data, features


class FakeS3:
    """Bucket versionado en memoria con la parte de la API de S3 que usamos."""

    def __init__(self, versioning="Enabled"):
        self.objects, self.puts, self.versioning = {}, 0, versioning

    def get_bucket_versioning(self, Bucket):
        return {"Status": self.versioning} if self.versioning else {}

    def put_object(self, Bucket, Key, Body, Metadata=None, **_):
        self.puts += 1
        version = f"v{self.puts}"
        self.objects[(Bucket, Key)] = (bytes(Body), version, Metadata or {})
        return {"VersionId": version}

    def get_object(self, Bucket, Key, VersionId=None):
        body, version, metadata = self.objects[(Bucket, Key)]
        return {"Body": io.BytesIO(body), "VersionId": version, "Metadata": metadata}

    def head_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        _, version, metadata = self.objects[(Bucket, Key)]
        return {"VersionId": version, "Metadata": metadata}


def test_resolve_expande_variables(monkeypatch):
    monkeypatch.setenv("MLOPS_DATA_BUCKET", "mi-bucket")
    assert data.resolve("s3://${MLOPS_DATA_BUCKET}/raw/202611") == "s3://mi-bucket/raw/202611"


def test_resolve_falla_si_falta_variable(monkeypatch):
    monkeypatch.delenv("MLOPS_DATA_BUCKET", raising=False)
    with pytest.raises(ValueError, match="MLOPS_DATA_BUCKET"):
        data.resolve("s3://${MLOPS_DATA_BUCKET}/raw")


def test_join_s3_y_local(tmp_path):
    assert data.join("s3://b/raw/202611/", "a.csv") == "s3://b/raw/202611/a.csv"
    assert data.join("s3://b/scores", 202408, "scores.csv") == "s3://b/scores/202408/scores.csv"
    assert data.join(tmp_path, "x", "a.csv") == str(tmp_path / "x" / "a.csv")


@pytest.mark.parametrize("uri", ["s3://", "s3://bucket", "s3://bucket/", "https://b/k"])
def test_split_s3_rechaza_uris_incompletas(uri):
    with pytest.raises(ValueError):
        data.split_s3(uri)


def test_parquet_en_s3_conserva_datos_y_version():
    s3 = FakeS3()
    df = pd.DataFrame({"ID_CORRELATIVO": [1, 2], "X": [0.5, 1.5]})
    written = data.write_parquet(df, "s3://b/features/202611/train.parquet", client=s3)
    read, info = data.read_parquet("s3://b/features/202611/train.parquet", client=s3)
    pd.testing.assert_frame_equal(read, df)
    assert info["version_id"] == written["version_id"] == "v1"
    assert info["sha256"] == written["sha256"]
    assert s3.objects[("b", "features/202611/train.parquet")][2]["sha256"] == info["sha256"]


def test_csv_local_registra_sha_y_filas(tmp_path):
    path = tmp_path / "a.csv"
    path.write_text("ID,X\n1,2\n3,4\n")
    df, info = data.read_csv(path)
    assert len(df) == info["rows"] == 2
    assert info["version_id"] is None
    assert info["sha256"] == data.sha256(path.read_bytes())


def test_check_against_manifest_detecta_otro_contenido():
    manifest = {"files": [{"filename": "a.csv", "sha256": "abc"}]}
    data.check_against_manifest({"sha256": "abc"}, "a.csv", manifest)
    with pytest.raises(ValueError, match="no coincide"):
        data.check_against_manifest({"sha256": "otro"}, "a.csv", manifest)


def _raw_release(tmp_path, content=b"ID,X\n1,2\n"):
    origin = tmp_path / "raw"
    origin.mkdir()
    (origin / "a.csv").write_bytes(content)
    manifest = tmp_path / "manifiesto.json"
    manifest.write_text(json.dumps({
        "dataset_release": "202611",
        "files": [{"filename": "a.csv", "sha256": data.sha256(content), "row_count": 1,
                   "version_id": None}],
    }))
    return origin, manifest


def test_upload_raw_registra_version_y_es_idempotente(tmp_path):
    s3 = FakeS3()
    origin, manifest = _raw_release(tmp_path)
    first = data.upload_raw(origin, "s3://b/raw/202611", manifest, client=s3)
    second = data.upload_raw(origin, "s3://b/raw/202611", manifest, client=s3)
    entry = json.loads(manifest.read_text())["files"][0]
    assert first["archivos"][0]["accion"] == "subido"
    assert second["archivos"][0]["accion"] == "sin cambios"
    assert s3.puts == 1
    assert entry["version_id"] == "v1"
    assert entry["source_uri"] == "s3://b/raw/202611/a.csv"


def test_upload_raw_no_sobrescribe_otra_version(tmp_path):
    s3 = FakeS3()
    s3.put_object(Bucket="b", Key="raw/202611/a.csv", Body=b"otro", Metadata={"sha256": "x"})
    origin, manifest = _raw_release(tmp_path)
    with pytest.raises(ValueError, match="inmutables"):
        data.upload_raw(origin, "s3://b/raw/202611", manifest, client=s3)
    assert s3.puts == 1


def test_upload_raw_rechaza_archivo_distinto_al_manifiesto(tmp_path):
    origin, manifest = _raw_release(tmp_path)
    (origin / "a.csv").write_bytes(b"ID,X\n9,9\n")
    with pytest.raises(ValueError, match="no coincide con el manifiesto"):
        data.upload_raw(origin, "s3://b/raw/202611", manifest, client=FakeS3())


@pytest.mark.parametrize("versioning", [None, "Suspended"])
def test_upload_raw_exige_versionado_antes_de_escribir(tmp_path, versioning):
    s3 = FakeS3(versioning=versioning)
    origin, manifest = _raw_release(tmp_path)
    with pytest.raises(ValueError, match="versionado"):
        data.upload_raw(origin, "s3://b/raw/202611", manifest, client=s3)
    assert s3.puts == 0
    assert json.loads(manifest.read_text())["files"][0]["version_id"] is None


def test_upload_raw_exige_el_diccionario(tmp_path):
    s3 = FakeS3()
    origin, manifest = _raw_release(tmp_path)
    content = json.loads(manifest.read_text())
    content["files"].append({"filename": "diccionario_datos.xlsx", "sha256": "abc"})
    manifest.write_text(json.dumps(content))
    with pytest.raises(FileNotFoundError, match="diccionario_datos.xlsx"):
        data.upload_raw(origin, "s3://b/raw/202611", manifest, client=s3)
    assert s3.puts == 0


def test_upload_raw_exige_carpeta_de_la_version(tmp_path):
    origin, manifest = _raw_release(tmp_path)
    with pytest.raises(ValueError, match="/202611"):
        data.upload_raw(origin, "s3://b/raw/202512", manifest, client=FakeS3())


def test_features_run_lee_s3_y_guarda_linaje(tmp_path, monkeypatch):
    monkeypatch.setenv("MLOPS_DATA_BUCKET", "b")
    s3 = FakeS3()
    lags = {f"SDO_ACTIVO_MENOS{i}": [10.0 * i, 1.0] for i in range(6)}
    cli = pd.DataFrame({"ID_CORRELATIVO": [1, 2], "CODMES": [202407] * 2, "ATTRITION": [0, 1],
                        **lags})
    req = pd.DataFrame({"ID_CORRELATIVO": [1], "TIPO_REQUERIMIENTO2": ["Reclamo"],
                        "DICTAMEN": ["NO PROCEDE"], "CODMES": [202407],
                        "PRODUCTO_SERVICIO_2": ["Producto 20"], "SUBMOTIVO_2": ["Submotivo 125"]})
    for name, frame in {"cli.csv": cli, "req.csv": req}.items():
        data.write_csv(frame, f"s3://b/raw/202611/{name}", client=s3)
    config = {
        "data": {"raw_path": "s3://${MLOPS_DATA_BUCKET}/raw/202611", "data_version": "202611",
                 "clientes_train": "cli.csv", "req_train": "req.csv",
                 "id_col": "ID_CORRELATIVO"},
        "features": {"output_path": "s3://${MLOPS_DATA_BUCKET}/features/202611",
                     "n_meses_req": 5, "corte": {"train": 202407},
                     "top_productos": ["Producto 20"], "top_submotivos": ["Submotivo 125"],
                     "tipos_req": ["Reclamo", "Solicitud"],
                     "dictamenes": ["NO PROCEDE", "SIN_DICTAMEN"],
                     "lag_prefixes": ["SDO_ACTIVO"]},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config))

    out = features.run("train", str(config_path), client=s3)

    df, info = data.read_parquet(out, client=s3)
    lineage = data.read_json("s3://b/features/202611/train_lineage.json", client=s3)
    assert len(df) == 2 and df.loc[0, "REQ_TOTAL"] == 1
    assert lineage["features"]["sha256"] == info["sha256"]
    assert [r["uri"] for r in lineage["raw"]] == ["s3://b/raw/202611/cli.csv",
                                                  "s3://b/raw/202611/req.csv"]
    assert all(r["version_id"] and r["sha256"] for r in lineage["raw"])
