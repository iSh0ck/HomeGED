import React from "react";
import { AlertOctagon, RefreshCw, RotateCcw } from "lucide-react";
import { t } from "../lib/langue";

/**
 * Barrière d'erreur : ce qui reste à l'écran quand un écran se casse.
 *
 * Sans elle, une exception pendant le rendu emporte l'application entière et
 * laisse une **page blanche** — ni message, ni bouton, ni indice. C'est arrivé
 * trois fois sur ce projet (une variable déclarée dans le mauvais composant, un
 * import oublié, des données mal formées), et chaque fois le symptôme rapporté a
 * été le même : « plus rien ne charge ». Une page blanche ne dit pas quoi faire,
 * et ne dit pas non plus quoi rapporter.
 *
 * Elle est posée **par écran** : le registre peut tomber sans emporter la
 * navigation ni la barre d'outils, et l'on s'en va ailleurs plutôt que de
 * recharger. Une dernière barrière entoure l'application, pour ce qui casserait
 * en dehors d'un écran.
 *
 * **Ce qu'elle ne rattrape pas**, et il faut le savoir : les erreurs des
 * gestionnaires d'événements et du code asynchrone. React ne les lui passe pas.
 * Un clic qui échoue ou un appel d'API qui tombe se traitent là où ils ont lieu
 * — c'est le rôle des fenêtres d'alerte (`AlerteModale`).
 *
 * Une classe et non une fonction : React ne propose `componentDidCatch` qu'aux
 * composants de classe. C'est le seul de tout le projet.
 */
export default class BarriereErreur extends React.Component {
  constructor(props) {
    super(props);
    this.state = { erreur: null };
  }

  static getDerivedStateFromError(erreur) {
    return { erreur };
  }

  componentDidCatch(erreur, infos) {
    // La console garde la pile complète : c'est ce qu'on demandera de copier.
    console.error(t("Écran interrompu :"), erreur, infos?.componentStack);
  }

  render() {
    if (!this.state.erreur) return this.props.children;

    const { titre = t("Cet écran s'est interrompu"), onReprendre } = this.props;
    const message = String(this.state.erreur?.message || this.state.erreur);

    return (
      <div style={cadre} role="alert">
        <div style={panneau}>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <AlertOctagon size={20} color="var(--brick)" style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--ink)" }}>{titre}</div>
              <div style={{ fontSize: 13, color: "var(--ink-soft)", lineHeight: 1.55, marginTop: 6 }}>
                {t("Rien n'est perdu : vos documents sont en base, et cette interruption n'a touché que l'affichage. Reprenez ci-dessous, ou changez d'écran.")}
              </div>
            </div>
          </div>

          {/* Le message technique est montré, replié dans un cadre discret : il
              ne sert à rien sur le moment, et à tout quand on le rapporte. */}
          <pre style={technique}>{message}</pre>

          <div style={{ display: "flex", gap: 8, marginTop: 16, flexWrap: "wrap" }}>
            <button onClick={() => this.setState({ erreur: null })} style={boutonPrimaire}>
              <RotateCcw size={14} />
              Réessayer
            </button>
            {onReprendre && (
              <button
                onClick={() => { this.setState({ erreur: null }); onReprendre(); }}
                style={boutonSecondaire}
              >
                Revenir à l'accueil
              </button>
            )}
            <button onClick={() => window.location.reload()} style={boutonSecondaire}>
              <RefreshCw size={14} />
              Recharger la page
            </button>
          </div>
        </div>
      </div>
    );
  }
}

const cadre = {
  flex: 1, display: "flex", alignItems: "flex-start", justifyContent: "center",
  padding: "48px 24px", overflowY: "auto", background: "var(--bg-app)",
};

const panneau = {
  width: "100%", maxWidth: 560, padding: 20,
  background: "var(--bg-panel)", border: "1px solid var(--line)",
  borderRadius: "var(--radius)", boxShadow: "var(--shadow-panel)",
};

const technique = {
  marginTop: 14, marginBottom: 0, padding: "9px 11px",
  background: "var(--bg-panel-alt)", border: "1px solid var(--line)",
  borderRadius: "var(--radius)", fontSize: 11.5, color: "var(--ink-soft)",
  whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: 160, overflow: "auto",
};

const commun = {
  display: "inline-flex", alignItems: "center", gap: 6,
  borderRadius: "var(--radius)", padding: "7px 13px", fontSize: 13,
};

const boutonPrimaire = { ...commun, border: "none", background: "var(--accent)", color: "#fff", fontWeight: 600 };
const boutonSecondaire = {
  ...commun, border: "1px solid var(--line-strong)", background: "transparent",
  color: "var(--ink-soft)",
};
