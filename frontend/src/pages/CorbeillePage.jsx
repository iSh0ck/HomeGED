import React, { useEffect, useState } from "react";
import { ArrowLeft, RotateCcw, Trash2, EyeOff } from "lucide-react";
import { api } from "../api";
import { formaterHorodatage, ilYA } from "../lib/horodatage";
import { t } from "../lib/langue";
import Pagination from "../components/Pagination.jsx";

/**
 * Ma corbeille (§21.1).
 *
 * Supprimer un document effaçait tout, sur-le-champ : la fiche, ses métadonnées,
 * et le fichier au passage suivant du serveur de travaux. Dans une maison où
 * chacun a le droit de supprimer, une fausse manœuvre ne se rattrapait pas.
 *
 * Chacun retrouve ici ce qu'il a jeté, et le remet à sa place — exactement celle
 * qu'il occupait. Le second bouton, « retirer », ne détruit rien : il sort le
 * document de cette vue, où il encombre, et le laisse à l'administration, seule
 * à pouvoir l'effacer pour de bon. Une corbeille qui détruit au second clic
 * n'est plus un filet.
 */
export default function CorbeillePage({ onRetour, onChangement }) {
  const [documents, setDocuments] = useState(null);
  const [total, setTotal] = useState(0);
  const [erreur, setErreur] = useState(null);
  const [enCours, setEnCours] = useState(null);
  const [vidage, setVidage] = useState(false);
  // Paginée (§22.90) : la liste s'arrêtait à 500 sans le dire, et les plus
  // anciens n'étaient plus récupérables depuis cet écran.
  const [parPage, setParPage] = useState(25);
  const [decalage, setDecalage] = useState(0);

  function charger() {
    api.corbeille({ limite: parPage, decalage })
      .then((page) => { setDocuments(page.documents || []); setTotal(page.total || 0); })
      .catch((e) => setErreur(e.message));
  }
  useEffect(charger, [parPage, decalage]);

  async function agir(document, action) {
    setEnCours(document.id);
    setErreur(null);
    try {
      await (action === "restaurer"
        ? api.restaurerDocument(document.id)
        : api.retirerDeLaCorbeille(document.id));
      // Retirer la dernière ligne d'une page laisserait une page blanche : on
      // recule d'un cran plutôt que de laisser chercher.
      if (documents?.length === 1 && decalage > 0) setDecalage(decalage - parPage);
      else charger();
      onChangement?.();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(null);
    }
  }

  /**
   * Tout retirer d'un coup (§21.14).
   *
   * Comme le geste unitaire, cela ne détruit rien : les documents passent en
   * masqué et restent accessibles à l'administration. Vider sa corbeille est un
   * geste de rangement — on ne veut plus les voir là —, pas une destruction ;
   * c'est ce qui rend le bouton sans danger.
   */
  async function vider() {
    setEnCours("tout");
    setErreur(null);
    try {
      await api.viderMaCorbeille();
      setVidage(false);
      charger();
      onChangement?.();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(null);
    }
  }

  return (
    <div style={{ padding: "20px 26px", overflowY: "auto", flex: 1 }} className="scrollbar-thin">
      <button
        onClick={onRetour}
        style={{ display: "flex", alignItems: "center", gap: 6, border: "none",
                 background: "transparent", color: "var(--accent)", fontSize: 12.5,
                 padding: 0, marginBottom: 14, cursor: "pointer" }}
      >
        <ArrowLeft size={14} />
        Retour au registre
      </button>

      <h2 style={{ fontSize: 16, marginBottom: 4 }}>{t("Ma corbeille")}</h2>
      <p style={{ fontSize: 12.5, color: "var(--ink-soft)", lineHeight: 1.55,
                  maxWidth: 640, marginBottom: 18 }}>
        {t("Ce que vous avez supprimé attend ici. Rien n'est perdu : un document restauré retrouve exactement sa place, ses champs et ses versions. « Retirer » ne détruit pas non plus — le document quitte cette liste et reste accessible à l'administration.")}
      </p>

      {erreur && (
        <div style={{ fontSize: 12.5, color: "var(--brick)", marginBottom: 12 }}>{erreur}</div>
      )}

      {documents === null && !erreur && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>{t("Chargement…")}</div>
      )}

      {documents?.length === 0 && (
        <div style={{ fontSize: 12.5, color: "var(--ink-faint)" }}>
          {t("Votre corbeille est vide.")}
        </div>
      )}

      {documents?.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <button
            onClick={() => (vidage ? vider() : setVidage(true))}
            disabled={enCours === "tout"}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              border: `1px solid ${vidage ? "var(--brick)" : "var(--line-strong)"}`,
              background: vidage ? "var(--brick)" : "transparent",
              color: vidage ? "#fff" : "var(--ink-soft)",
              borderRadius: "var(--radius)", padding: "6px 12px", fontSize: 12.5,
              cursor: "pointer",
            }}
          >
            <EyeOff size={13} />
            {vidage
              ? `Confirmer : retirer les ${documents.length} de ma liste`
              : t("Tout retirer de ma corbeille")}
          </button>
          {vidage && (
            <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>
              {t("Rien n'est détruit : l'administration pourra encore les récupérer.")}
            </span>
          )}
        </div>
      )}

      {documents?.length > 0 && (
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--radius)",
                      overflow: "hidden" }}>
          {documents.map((doc, index) => (
            <div
              key={doc.id}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                borderBottom: index < documents.length - 1 ? "1px solid var(--line)" : "none",
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap" }}>
                  {doc.libelle || doc.nom_fichier}
                </div>
                {/* De quoi reconnaître **ce** document-là parmi ses semblables
                    (§22.63) : « Factures · supprimé il y a 3 min » ne dit pas
                    laquelle on s'apprête à perdre, et c'est pourtant la seule
                    question qu'on se pose devant une corbeille. */}
                {doc.details?.length > 0 && (
                  <div style={{ fontSize: 11.5, color: "var(--ink-soft)", marginTop: 2,
                                display: "flex", flexWrap: "wrap", gap: 10 }}>
                    {doc.details.map((d) => (
                      <span key={d.libelle}>
                        <span style={{ color: "var(--ink-faint)" }}>{t(d.libelle)} </span>
                        {d.valeur}
                      </span>
                    ))}
                  </div>
                )}
                <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 2 }}>
                  {doc.categorie || t("sans classement")}
                  {" · "}{t("supprimé")}{" "}
                  <span title={formaterHorodatage(doc.date_suppression)}>
                    {ilYA(doc.date_suppression)}
                  </span>
                  {doc.supprime_par && <>{" "}{t("par {qui}", { qui: doc.supprime_par })}</>}
                </div>
              </div>

              <button
                onClick={() => agir(doc, "restaurer")}
                disabled={enCours === doc.id}
                style={boutonAction}
              >
                <RotateCcw size={13} />
                Restaurer
              </button>
              <button
                onClick={() => agir(doc, "retirer")}
                disabled={enCours === doc.id}
                title={t("Le retirer de cette liste. L'administration pourra encore le récupérer.")}
                style={{ ...boutonAction, color: "var(--ink-faint)" }}
              >
                <EyeOff size={13} />
                Retirer
              </button>
            </div>
          ))}
        </div>
      )}

      {total > 0 && (
        <Pagination
          total={total}
          parPage={parPage}
          decalage={decalage}
          onDecalage={setDecalage}
          // Changer le nombre par page renvoie au début : rester au même
          // décalage ferait atterrir ailleurs que là où on croit être.
          onParPage={(n) => { setParPage(n); setDecalage(0); }}
        />
      )}
    </div>
  );
}

const boutonAction = {
  display: "inline-flex", alignItems: "center", gap: 5,
  border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)", borderRadius: "var(--radius)",
  padding: "5px 10px", fontSize: 12, cursor: "pointer", flexShrink: 0,
};

/** Le bouton d'accès, avec son compteur — une corbeille qu'on ne voit pas ne se vide jamais. */
export function BoutonCorbeille({ nombre = 0, onClick }) {
  if (!nombre) return null;
  return (
    <button
      onClick={onClick}
      title={`${nombre} document${nombre > 1 ? "s" : ""} dans votre corbeille`}
      style={{
        display: "flex", alignItems: "center", gap: 6, background: "transparent",
        color: "var(--ink-soft)", border: "1px solid var(--line-strong)",
        borderRadius: "var(--radius)", padding: "7px 12px", fontSize: 13,
      }}
    >
      <Trash2 size={15} />
      {nombre}
    </button>
  );
}
