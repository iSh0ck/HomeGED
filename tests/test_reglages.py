

def test_le_nombre_de_traitements_simultanes_se_regle_et_se_relit(client):
    """
    Le parallélisme du serveur de travaux se règle depuis l'administration
    (§22.41) : il dépend de la machine du foyer, et personne d'autre que celui
    qui l'administre ne peut l'arbitrer. Zéro veut dire « décide pour moi ».
    """
    from app import worker
    from app.db import SessionLocal

    session = SessionLocal()
    try:
        assert worker.parallelisme_voulu(session) == worker.parallelisme_par_defaut()

        reponse = client.put("/admin/reglages", json={"traitements_simultanes": "3"})
        assert reponse.status_code == 200, reponse.text
        assert worker.parallelisme_voulu() == 3

        # Un nombre déraisonnable est ramené dans les clous plutôt que refusé :
        # le réglage ne doit pas pouvoir mettre la machine à terre.
        client.put("/admin/reglages", json={"traitements_simultanes": "99"})
        assert worker.parallelisme_voulu() <= 8
    finally:
        client.put("/admin/reglages", json={"traitements_simultanes": "0"})
        session.close()


def test_un_choix_technique_se_lit_par_son_intitule(client):
    """
    Le tri par défaut proposait « date_document » et « nom_fichier » (§22.70) :
    des noms de colonnes que personne n'écrit et que tout le monde devait
    deviner. Les intitulés viennent de `colonnes.LIBELLES_SYSTEME`, ceux-là mêmes
    que le registre affiche en tête de colonne — les récrire les ferait diverger.
    """
    from app import colonnes

    champs = client.get("/admin/reglages").json()["champs"]
    tri = next(c for c in champs if c["cle"] == "tri_defaut_champ")

    assert tri["libelles_options"]["date_document"] == "Date du document"
    assert set(tri["options"]) <= set(tri["libelles_options"]), \
        "toute option de ce choix doit pouvoir se lire"
    assert tri["libelles_options"] == colonnes.LIBELLES_SYSTEME, \
        "une seule source d'intitulés, sans quoi les deux écrans divergeront"


def test_un_choix_lisible_n_a_pas_besoin_d_intitules(client):
    """« auto », « papier », « compacte » se lisent seuls : rien à ajouter."""
    champs = client.get("/admin/reglages").json()["champs"]
    densite = next(c for c in champs if c["cle"] == "densite")
    assert densite["libelles_options"] == {}
