"""Contrato de la API: entrada válida -> 200 con el esquema esperado; entradas inválidas -> 422 con el campo."""
from conftest import a_json

CAMPOS_RESPUESTA = {"id_prediccion", "trans_num", "probabilidad", "decision", "umbral_verificar", "umbral_retener",
                    "modelo", "version_modelo", "alias", "run_id", "respaldo", "motivo_respaldo", "latencia_ms",
                    "timestamp_utc"}


def test_entrada_valida_devuelve_200_con_el_esquema(api, muestra):
    r = api.post("/predecir", json=a_json(muestra.iloc[0]))
    assert r.status_code == 200
    cuerpo = r.json()
    assert set(cuerpo) == CAMPOS_RESPUESTA
    assert 0.0 <= cuerpo["probabilidad"] <= 1.0
    assert cuerpo["decision"] in {"aprobar", "verificar", "retener"}
    assert cuerpo["respaldo"] is False and cuerpo["version_modelo"] == "1"


def test_decision_respeta_los_dos_umbrales(api, muestra):
    for _, fila in muestra.sample(60, random_state=0).iterrows():
        c = api.post("/predecir", json=a_json(fila)).json()
        p, u1, u2 = c["probabilidad"], c["umbral_verificar"], c["umbral_retener"]
        esperada = "retener" if p >= u2 else ("verificar" if p >= u1 else "aprobar")
        assert c["decision"] == esperada


def _error(api, cuerpo):
    r = api.post("/predecir", json=cuerpo)
    assert r.status_code == 422
    return r.json()


def test_campo_faltante_devuelve_422(api, muestra):
    cuerpo = a_json(muestra.iloc[0]); del cuerpo["amt"]
    e = _error(api, cuerpo)
    assert any(x["campo"] == "amt" for x in e["errores"]) and "amt" in e["mensaje"]


def test_tipo_incorrecto_devuelve_422(api, muestra):
    e = _error(api, {**a_json(muestra.iloc[0]), "amt": "mil dólares"})
    assert any(x["campo"] == "amt" for x in e["errores"])


def test_categoria_desconocida_devuelve_422(api, muestra):
    e = _error(api, {**a_json(muestra.iloc[0]), "categoria": "casino"})
    assert any(x["campo"] == "categoria" for x in e["errores"])


def test_fuera_de_rango_y_campo_extra_devuelven_422(api, muestra):
    assert any(x["campo"] == "hora" for x in _error(api, {**a_json(muestra.iloc[0]), "hora": 25})["errores"])
    assert any(x["campo"] == "montoo" for x in _error(api, {**a_json(muestra.iloc[0]), "montoo": 1})["errores"])


def test_lote_devuelve_una_prediccion_con_id_por_fila(api, muestra):
    filas = [a_json(f) for _, f in muestra.head(25).iterrows()]
    r = api.post("/predecir_lote", json={"lote": 7, "transacciones": filas})
    assert r.status_code == 200
    preds = r.json()["predicciones"]
    assert len(preds) == 25 and len({p["id_prediccion"] for p in preds}) == 25
    assert [p["trans_num"] for p in preds] == [f["trans_num"] for f in filas]


def test_modelo_y_salud_informan_version_y_run_id(api, esperadas):
    m = api.get("/modelo").json()
    assert m["version"] == esperadas["version"] and m["run_id"] == esperadas["run_id"]
    assert api.get("/salud").json()["modelo_cargado"] is True
