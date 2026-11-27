"""Respaldo: si el modelo no carga, la API responde con las reglas fijas del PSet 1 e indica respaldo=true.
El interruptor protegido (/respaldo con X-Token) fuerza el mismo modo."""
import pytest

from conftest import a_json


def test_modelo_que_no_carga_responde_con_reglas(api, muestra, monkeypatch):
    import main
    roto = main.GestorModelo("/ruta/que/no/existe")
    assert roto.cargar() is False and roto.modelo is None
    monkeypatch.setattr(main, "gestor", roto)
    r = api.post("/predecir", json=a_json(muestra.iloc[0]))
    assert r.status_code == 200
    c = r.json()
    assert c["respaldo"] is True and c["probabilidad"] is None and c["modelo"] == "reglas_fijas_pset1"
    assert c["decision"] in {"aprobar", "verificar"} and "no cargado" in c["motivo_respaldo"]
    assert api.get("/salud").json()["modelo_cargado"] is False


def test_reglas_del_respaldo_coinciden_con_las_del_pset1(muestra):
    import main
    X = muestra.drop(columns=["trans_num", "is_fraud", "probabilidad_esperada"])
    alerta = main.reglas_fijas(X)
    p95 = X["categoria"].map(main.CATALOGOS["p95_amt_por_categoria"])
    esperado = (X["amt"] > p95) | (X["es_nocturna"] & (X["amt"] >= 100)) | (X["distancia_km"] > 100)
    assert (alerta == esperado.to_numpy()).all()


def test_interruptor_exige_token_y_fuerza_el_respaldo(api, muestra):
    assert api.post("/respaldo", json={"activo": True}).status_code == 401
    assert api.post("/respaldo", json={"activo": True}, headers={"X-Token": "otro"}).status_code == 401
    try:
        r = api.post("/respaldo", json={"activo": True}, headers={"X-Token": "token-de-prueba"})
        assert r.status_code == 200 and r.json()["respaldo"] is True
        c = api.post("/predecir", json=a_json(muestra.iloc[0])).json()
        assert c["respaldo"] is True and c["motivo_respaldo"] == "interruptor de respaldo activado"
    finally:
        api.post("/respaldo", json={"activo": False}, headers={"X-Token": "token-de-prueba"})
    assert api.post("/predecir", json=a_json(muestra.iloc[0])).json()["respaldo"] is False
