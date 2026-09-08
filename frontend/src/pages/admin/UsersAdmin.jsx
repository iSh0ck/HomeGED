import React, { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, RotateCcw, Eye } from "lucide-react";
import { adminApi, retenirConsultation } from "../../api";
import AdminTable from "../../components/AdminTable.jsx";
import Modal, { champStyle, inputStyle, boutonPrimaire } from "../../components/Modal.jsx";
import ConfirmerSuppression from "../../components/ConfirmerSuppression.jsx";
import AlerteModale from "../../components/AlerteModale.jsx";
import { t } from "../../lib/langue";

/**
 * Ce compte est-il le seul administrateur encore actif ?
 *
 * On le calcule sur la liste affichée plutôt que de le demander à l'API : c'est
 * la même information, elle est déjà là, et l'avertissement doit apparaître au
 * moment où l'on décoche — pas après un aller-retour.
 */
function estLeDernierAdmin(edition, utilisateurs) {
  if (!edition?.id) return false;
  const autres = (utilisateurs || []).filter(
    (u) => u.id !== edition.id && u.est_admin && u.actif);
  const etaitAdminActif = (utilisateurs || []).some(
    (u) => u.id === edition.id && u.est_admin && u.actif);
  return etaitAdminActif && autres.length === 0;
}

const VIDE = { email: "", nom: "", prenom: "", mot_de_passe: "", est_admin: false, actif: true,
               otp_impose: false, role_ids: [] };

export default function UsersAdmin() {
  const [utilisateurs, setUtilisateurs] = useState([]);
  const [roles, setRoles] = useState([]);
  const [edition, setEdition] = useState(null);
  const [erreur, setErreur] = useState(null);
  const [alerte, setAlerte] = useState(null);
  const [suppression, setSuppression] = useState(null);
  const [reinitialisation, setReinitialisation] = useState(null);

  function charger() {
    adminApi.utilisateurs().then(setUtilisateurs).catch((e) => setErreur(e.message));
    adminApi.roles().then(setRoles).catch(() => {});
  }
  useEffect(charger, []);

  function ouvrirEdition(u) {
    const role_ids = roles.filter((r) => u.roles.includes(r.nom)).map((r) => r.id);
    setEdition({ ...u, role_ids, mot_de_passe: "" });
  }

  async function enregistrer(e) {
    e.preventDefault();
    setErreur(null);
    try {
      const payload = {
        email: edition.email,
        nom: edition.nom,
        prenom: edition.prenom,
        est_admin: !!edition.est_admin,
        actif: !!edition.actif,
        otp_impose: !!edition.otp_impose,
        role_ids: edition.role_ids || [],
        mot_de_passe: edition.mot_de_passe || undefined,
      };
      if (edition.id) await adminApi.modifierUtilisateur(edition.id, payload);
      else await adminApi.creerUtilisateur(payload);
      setEdition(null);
      charger();
    } catch (err) {
      // Perdre le dernier administrateur ferme l'administration à tout le monde,
      // et le compte initial n'est recréé que sur une base vide : ce refus mérite
      // une fenêtre qu'on acquitte, pas une ligne rouge sous un formulaire qu'on
      // vient de faire défiler.
      if (/dernier administrateur/i.test(err.message || "")) setAlerte(err.message);
      else setErreur(err.message);
    }
  }

  async function supprimer() {
    await adminApi.supprimerUtilisateur(suppression.id).catch((e) => {
      if (/dernier administrateur/i.test(e.message || "")) setAlerte(e.message);
      else setErreur(e.message);
    });
    charger();
    setSuppression(null);
  }

  function basculerRole(roleId) {
    const ids = edition.role_ids || [];
    setEdition({
      ...edition,
      role_ids: ids.includes(roleId) ? ids.filter((id) => id !== roleId) : [...ids, roleId],
    });
  }

  /**
   * Ouvre le registre sous l'identité d'un autre compte (§18.50).
   *
   * Rechargement franc plutôt que changement d'état : l'identité de l'appelant
   * change, et tout ce que la page a déjà chargé — catégories visibles, vues,
   * droits — porte sur quelqu'un d'autre. Repartir de zéro est ici la seule
   * façon d'être sûr de ce qu'on regarde.
   */
  async function consulter(utilisateur) {
    setErreur(null);
    try {
      const ouverture = await adminApi.ouvrirConsultation(utilisateur.id);
      retenirConsultation({ jeton: ouverture.jeton, ...ouverture.utilisateur });
      window.location.assign("/");
    } catch (e) {
      setErreur(e.message);
    }
  }

  return (
    <div>
      <p style={{ fontSize: 13, color: "var(--ink-soft)", marginBottom: 16 }}>
        {t("Un administrateur voit et modifie toutes les catégories. Les autres comptes héritent des droits des rôles qui leur sont attribués (configurés dans l'onglet « Rôles & droits ») — pratique pour donner accès à une seule personne du foyer sans lui ouvrir tous les documents.")}
      </p>

      <AdminTable
        libelleAjout={t("Nouvel utilisateur")}
        onAjouter={() => setEdition({ ...VIDE })}
        onModifier={ouvrirEdition}
        onSupprimer={setSuppression}
        colonnes={[
          { key: "nom_affiche", label: "Nom" },
          { key: "email", label: t("E-mail") },
          {
            key: "est_admin",
            label: t("Rôle système"),
            render: (u) => (u.est_admin ? "Administrateur" : "Standard"),
          },
          {
            key: "roles",
            label: t("Rôles"),
            render: (u) => (u.roles.length ? u.roles.join(", ") : "—"),
          },
          {
            key: "actif",
            label: "Statut",
            render: (u) => (u.actif ? "Actif" : t("Désactivé")),
          },
          {
            key: "otp_actif",
            label: t("Double authentification"),
            render: (u) => <EtatOtp utilisateur={u} onReinitialiser={() => setReinitialisation(u)} />,
          },
          {
            key: "consultation",
            label: "Registre",
            render: (u) => (
              <button
                type="button"
                disabled={!u.actif}
                onClick={() => consulter(u)}
                title={u.actif
                  ? t("Ouvrir le registre tel que {qui} le voit",
                    { qui: `${u.prenom || ""} ${u.nom || ""}`.trim() })
                  : t("Un compte désactivé ne verrait rien")}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  border: "1px solid var(--line-strong)", background: "transparent",
                  color: u.actif ? "var(--ink-soft)" : "var(--ink-faint)",
                  borderRadius: "var(--radius)", padding: "3px 8px", fontSize: 12,
                  opacity: u.actif ? 1 : 0.5,
                }}
              >
                <Eye size={12} />
                Voir comme
              </button>
            ),
          },
        ]}
        lignes={utilisateurs}
      />

      {erreur && <div style={{ color: "var(--brick)", fontSize: 12, marginTop: 10 }}>{erreur}</div>}

      {alerte && (
        <AlerteModale
          titre={t("Il faut au moins un administrateur")}
          ton="attente"
          message={alerte}
          onFermer={() => setAlerte(null)}
        />
      )}

      {suppression && (
        <ConfirmerSuppression
          typeObjet={"utilisateur"}
          identifiant={suppression.id}
          intitule={`le compte « ${suppression.nom} »`}
          onAnnuler={() => setSuppression(null)}
          onConfirmer={supprimer}
        />
      )}

      {reinitialisation && (
        <Modal titre={t("Débloquer la double authentification")} onClose={() => setReinitialisation(null)} width={440}>
          <p style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 4 }}>
            Le second facteur de <strong>{reinitialisation.nom}</strong> sera retiré : ce
            compte se reconnectera avec son mot de passe seul, et ses codes de secours
            cesseront d'être valables. À faire quand le téléphone est perdu — et après
            s'être assuré que la demande vient bien de la personne.
            {reinitialisation.otp_impose && (
              <> L'exigence, elle, demeure : il devra en appairer une nouvelle à sa
              prochaine connexion.</>
            )}
          </p>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
            <button onClick={() => setReinitialisation(null)} style={{
              border: "1px solid var(--line-strong)", background: "transparent",
              color: "var(--ink-soft)", borderRadius: "var(--radius)", padding: "8px 14px", fontSize: 13,
            }}>
              Annuler
            </button>
            <button
              onClick={async () => {
                try {
                  await adminApi.reinitialiserOtp(reinitialisation.id);
                  charger();
                } catch (err) {
                  setErreur(err.message);
                }
                setReinitialisation(null);
              }}
              style={{ ...boutonPrimaire, marginTop: 0, background: "var(--brick)" }}
            >
              Débloquer
            </button>
          </div>
        </Modal>
      )}

      {edition && (
        <Modal titre={edition.id ? t("Modifier l'utilisateur") : t("Nouvel utilisateur")} onClose={() => setEdition(null)}>
          <form onSubmit={enregistrer}>
            <label style={champStyle}>
              Prénom {!edition.est_admin && <Obligatoire />}
            </label>
            <input
              required={!edition.est_admin}
              value={edition.prenom || ""}
              onChange={(e) => setEdition({ ...edition, prenom: e.target.value })}
              style={inputStyle}
            />

            <label style={champStyle}>
              Nom {!edition.est_admin && <Obligatoire />}
            </label>
            <input
              required={!edition.est_admin}
              value={edition.nom || ""}
              onChange={(e) => setEdition({ ...edition, nom: e.target.value })}
              style={inputStyle}
            />

            <label style={champStyle}>{t("E-mail")}</label>
            <input
              type="email"
              required
              value={edition.email}
              onChange={(e) => setEdition({ ...edition, email: e.target.value })}
              style={inputStyle}
            />

            <label style={champStyle}>
              Mot de passe {edition.id && t("(laisser vide pour ne pas changer)")}
            </label>
            <input
              type="password"
              required={!edition.id}
              value={edition.mot_de_passe}
              onChange={(e) => setEdition({ ...edition, mot_de_passe: e.target.value })}
              style={inputStyle}
            />

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.est_admin}
                onChange={(e) => setEdition({ ...edition, est_admin: e.target.checked })}
              />
              {t("Administrateur (accès total, ignore les rôles ci-dessous)")}
            </label>

            <label style={{ ...champStyle, display: "flex", alignItems: "center", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.actif}
                onChange={(e) => setEdition({ ...edition, actif: e.target.checked })}
              />
              Compte actif
            </label>

            {/* Prévenir avant, plutôt que refuser après : ce compte est le seul
                qui puisse encore administrer, et la case le dit maintenant —
                l'API refusera de toute façon, mais on ne fait pas remplir un
                formulaire pour rien. */}
            {estLeDernierAdmin(edition, utilisateurs) && (!edition.actif || !edition.est_admin) && (
              <div style={{
                display: "flex", gap: 9, padding: "9px 11px", marginTop: -6, marginBottom: 12,
                borderRadius: "var(--radius)", background: "var(--amber-soft)",
                border: "1px solid var(--amber)", fontSize: 12, color: "var(--ink)",
                lineHeight: 1.5,
              }}>
                <ShieldAlert size={15} color="var(--amber)" style={{ flexShrink: 0, marginTop: 1 }} />
                <div>
                  <strong>{t("C'est le dernier administrateur actif.")}</strong> Le désactiver ou le
                  rétrograder fermerait l'administration à tout le monde : nommez d'abord un
                  autre administrateur. L'enregistrement sera refusé.
                </div>
              </div>
            )}

            <label style={{ ...champStyle, display: "flex", alignItems: "flex-start", gap: 8 }}>
              <input
                type="checkbox"
                checked={!!edition.otp_impose}
                onChange={(e) => setEdition({ ...edition, otp_impose: e.target.checked })}
                style={{ marginTop: 2 }}
              />
              <span>
                Exiger la double authentification
                <span style={{ display: "block", fontSize: 11, color: "var(--ink-faint)", marginTop: 2 }}>
                  {t("Tant qu'elle n'est pas configurée, ce compte peut se connecter mais n'accède qu'à la page « Mon compte ».")}
                </span>
              </span>
            </label>

            {!edition.est_admin && (
              <>
                <label style={champStyle}>{t("Rôles")}</label>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {roles.length === 0 && (
                    <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                      {t("Aucun rôle créé pour l'instant — vas dans l'onglet « Rôles & droits ».")}
                    </div>
                  )}
                  {roles.map((r) => (
                    <label key={r.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                      <input
                        type="checkbox"
                        checked={(edition.role_ids || []).includes(r.id)}
                        onChange={() => basculerRole(r.id)}
                      />
                      {r.nom}
                    </label>
                  ))}
                </div>
              </>
            )}

            <button type="submit" style={boutonPrimaire}>Enregistrer</button>
          </form>
        </Modal>
      )}
    </div>
  );
}

/**
 * État de la double authentification d'un compte, et déblocage.
 *
 * Trois situations à distinguer : configurée, exigée mais pas encore en place
 * (le compte est bloqué hors de sa page « Mon compte »), et simplement absente.
 * Les confondre laisserait un administrateur sans savoir qui attend quoi.
 */
function EtatOtp({ utilisateur, onReinitialiser }) {
  const commun = { display: "flex", alignItems: "center", gap: 5, fontSize: 12 };

  if (utilisateur.otp_actif) {
    return (
      <span style={{ ...commun, justifyContent: "space-between" }}>
        <span style={{ ...commun, color: "var(--accent)" }}>
          <ShieldCheck size={13} />
          Active{utilisateur.otp_impose ? t(" · exigée") : ""}
        </span>
        <button
          onClick={onReinitialiser}
          title={t("Téléphone perdu : retirer le second facteur")}
          style={{
            display: "flex", alignItems: "center", gap: 4,
            border: "1px solid var(--line-strong)", background: "transparent",
            color: "var(--ink-soft)", borderRadius: "var(--radius)",
            padding: "2px 7px", fontSize: 11,
          }}
        >
          <RotateCcw size={11} />
          Débloquer
        </button>
      </span>
    );
  }

  if (utilisateur.otp_impose) {
    return (
      <span style={{ ...commun, color: "var(--amber)" }}>
        <ShieldAlert size={13} />
        {t("Exigée, pas encore configurée")}
      </span>
    );
  }
  return <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>Inactive</span>;
}

/**
 * Marque un champ exigé. Prénom et nom le sont pour les comptes du foyer — ce
 * sont eux qui permettent de rattacher un document à une personne — mais pas
 * pour un administrateur, qui est un rôle de gestion plutôt qu'un membre.
 */
function Obligatoire() {
  return <span style={{ color: "var(--brick)" }} title="Obligatoire">*</span>;
}
