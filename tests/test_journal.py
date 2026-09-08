

def test_la_configuration_du_classement_laisse_une_trace(client):
    """
    Documents, comptes et exports étaient tracés ; le classement, non (§22.48).
    Un champ attendu disparu ne se datait donc pas, ne s'attribuait pas et ne
    s'expliquait pas — constaté à nos dépens. Ce qui décide de la façon dont le
    foyer range mérite le même journal que ce qu'il range.
    """
    from app.db import Categorie, SessionLocal

    session = SessionLocal()
    try:
        type_doc = session.query(Categorie).filter(Categorie.nature == "type").first()
        categorie_id = type_doc.id
    finally:
        session.close()

    cree = client.post("/admin/regles-champs", json={
        "categorie_id": categorie_id, "champ": "meta:_trace_essai",
        "libelle": "Essai de trace", "obligatoire": True, "ordre": 900})
    assert cree.status_code == 200, cree.text
    identifiant = cree.json()["id"]

    client.put(f"/admin/regles-champs/{identifiant}", json={
        "categorie_id": categorie_id, "champ": "meta:_trace_essai",
        "libelle": "Essai renommé", "obligatoire": False, "ordre": 900})
    client.delete(f"/admin/regles-champs/{identifiant}")

    journal = client.get("/admin/audit?limite=200").json()
    lignes = journal["evenements"] if isinstance(journal, dict) else journal
    actions = [e["action"] for e in lignes]
    for attendue in ("champ_attendu.creation", "champ_attendu.modification",
                     "champ_attendu.suppression"):
        assert attendue in actions, f"« {attendue} » doit laisser une trace"

    # La trace de suppression doit porter de quoi **remonter** le champ : c'est
    # tout son intérêt.
    trace = next(e for e in lignes if e["action"] == "champ_attendu.suppression")
    details = trace.get("details") or {}
    if isinstance(details, str):
        import json as _json
        details = _json.loads(details)
    assert details.get("champ") == "meta:_trace_essai"
    assert "obligatoire" in details and "deduction" in details
