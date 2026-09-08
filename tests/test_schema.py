"""
Cohérence du schéma : `db/schema.sql` et les migrations doivent produire une
base saine. Ces contrôles auraient évité trois défauts constatés en service —
colonnes booléennes à NULL, clés étrangères en RESTRICT, index absents.
"""
from sqlalchemy import inspect

from app.db import engine


def _colonnes_booleennes(connexion, base):
    return connexion.exec_driver_sql(
        "SELECT TABLE_NAME, COLUMN_NAME, IS_NULLABLE, COLUMN_DEFAULT "
        "FROM information_schema.columns "
        "WHERE table_schema = %s AND DATA_TYPE = 'tinyint'", (base,)
    ).fetchall()


def test_toutes_les_migrations_sont_appliquees():
    with engine.connect() as connexion:
        versions = {v for (v,) in connexion.exec_driver_sql("SELECT version FROM sys_schema_migrations")}
    assert len(versions) >= 18, f"migrations appliquées : {sorted(versions)}"


# Les booléens à trois états, et pourquoi chacun l'est.
#
# La règle ci-dessous existe parce qu'un booléen à NULL se comporte comme faux
# **sans le dire** : une règle d'extraction dont `actif` vaut NULL n'est jamais
# appliquée, et rien ne le signale. Elle vaut donc pour tout ce qui **commande**
# un comportement.
#
# Une colonne qui ne fait que **rapporter** un fait a le droit d'ignorer ce
# fait : « on ne sait pas » est une réponse, et l'inventer serait pire.
TROIS_ETATS = {
    # D'où vient le document (§22.68). NULL pour ceux dont la tâche portant la
    # trace a été purgée avant qu'on la note : aucune icône ne s'affiche, ce qui
    # est plus honnête qu'un « arrivé tout seul » inventé.
    ("sys_documents", "depot_manuel"),
}


def test_les_booleens_ont_une_valeur_par_defaut(base_de_test):
    """
    Une colonne booléenne sans clause DEFAULT prend NULL lors d'une insertion en
    SQL brut. Une règle d'extraction dont `actif` vaut NULL n'est jamais
    appliquée : le symptôme est silencieux, d'où ce contrôle.

    Les colonnes qui rapportent au lieu de commander sont listées dans
    `TROIS_ETATS`, avec la raison. La liste doit rester courte : chaque entrée
    est une exception qu'on assume, pas un oubli qu'on range.
    """
    with engine.connect() as connexion:
        base = connexion.exec_driver_sql("SELECT DATABASE()").scalar()
        fautives = [
            (table, colonne)
            for table, colonne, nullable, defaut in _colonnes_booleennes(connexion, base)
            if (nullable == "YES" or defaut is None) and (table, colonne) not in TROIS_ETATS
        ]
    assert not fautives, f"colonnes booléennes sans NOT NULL DEFAULT : {fautives}"


def test_les_cles_etrangeres_ne_bloquent_pas_les_suppressions(base_de_test):
    """
    Une contrainte laissée en RESTRICT fait échouer la suppression d'une
    catégorie, d'un émetteur ou d'une règle encore référencés — en erreur 500.
    """
    with engine.connect() as connexion:
        base = connexion.exec_driver_sql("SELECT DATABASE()").scalar()
        restrictives = connexion.exec_driver_sql(
            "SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = %s AND DELETE_RULE = 'RESTRICT'", (base,)
        ).fetchall()
    assert not restrictives, f"contraintes en RESTRICT : {restrictives}"


def test_index_indispensables_presents(base_de_test):
    """
    L'index FULLTEXT conditionne la recherche plein texte : sans lui, `?q=`
    renvoyait une erreur 500.
    """
    index = {i["name"] for i in inspect(engine).get_indexes("sys_documents")}
    assert "ft_texte_ocr" in index
    assert "idx_documents_date_import" in index


def test_texte_ocr_accepte_un_document_volumineux(base_de_test):
    """TEXT plafonne à 64 Ko ; le texte océrisé d'un document long le dépasse."""
    with engine.connect() as connexion:
        base = connexion.exec_driver_sql("SELECT DATABASE()").scalar()
        type_colonne = connexion.exec_driver_sql(
            "SELECT DATA_TYPE FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = 'sys_documents' AND column_name = 'texte_ocr'",
            (base,)
        ).scalar()
    assert type_colonne == "longtext"


def test_unicite_des_metadonnees(base_de_test):
    """Une même clé ne doit pas pouvoir exister deux fois sur un document."""
    index = {i["name"]: i for i in inspect(engine).get_indexes("sys_metadonnees")}
    assert "uq_doc_cle" in index and index["uq_doc_cle"]["unique"]
