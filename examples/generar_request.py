import json

import pandas as pd

cli = pd.read_csv("data/raw/202611/oot_clientes_sample.csv")
req = pd.read_csv("data/raw/202611/oot_requerimientos_sample.csv")

def limpiar(d: dict) -> dict:
    return {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v)) for k, v in d.items()}

row = cli.iloc[0]
i = int(row.ID_CORRELATIVO)
body = {
    "id_cliente": i,
    "codmes_corte": 202408,
    "cliente": limpiar(row.drop(["ID_CORRELATIVO", "CODMES"]).to_dict()),
    "requerimientos": [
        limpiar(r) for r in req[req.ID_CORRELATIVO == i].drop(columns="ID_CORRELATIVO").to_dict("records")
    ],
}
with open("examples/request.json", "w", encoding="utf-8") as f:
    json.dump(body, f, indent=2, ensure_ascii=False)
print(f"examples/request.json generado (cliente {i}, {len(body['requerimientos'])} requerimientos)")