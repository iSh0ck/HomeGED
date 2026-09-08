import React, { useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { t } from "../lib/langue";

/**
 * Une bande où l'on glisse un fichier (§22.1, §22.2).
 *
 * Deux endroits en ont besoin, pour la même raison : rien n'y entre tout seul.
 * Une **fiche simple** n'a pas de dossier de dépôt (§22.1) ; une **pièce
 * jointe** ne vient d'aucun dossier — elle rejoint un document déjà classé
 * (§22.2). Dans les deux cas il faut une porte, et une seule.
 *
 * Elle reste visible même quand il y a déjà quelque chose : une zone qui ne
 * s'affiche que sur un contenant vide oblige à chercher où l'on dépose le
 * second fichier — et l'on finirait par déposer ailleurs.
 *
 * Le fichier n'apparaît pas dans la seconde : le serveur de travaux archive,
 * océrise, applique les règles. Le message le dit plutôt que de laisser croire à
 * un échec devant un écran inchangé.
 */
export default function ZoneDepot({ invitation, ariaLabel, envoyer, succes, onDepose,
                                   complement = null, multiple = true }) {
  const [survol, setSurvol] = useState(false);
  const [enCours, setEnCours] = useState(0);
  const [message, setMessage] = useState(null);
  const champFichier = useRef(null);

  async function deposer(fichiers) {
    const liste = Array.from(fichiers || []);
    if (liste.length === 0) return;
    setMessage(null);
    setEnCours(liste.length);
    const refus = [];
    let acceptes = 0;
    for (const fichier of liste) {
      try {
        await envoyer(fichier);
        acceptes += 1;
      } catch (e) {
        refus.push(`${fichier.name} : ${t(e.message)}`);
      }
      setEnCours((n) => n - 1);
    }
    setMessage(
      refus.length === 0
        ? { ton: "ok", texte: succes(acceptes) }
        : { ton: "erreur", texte: refus.join(" · ") });
    if (acceptes > 0) onDepose?.();
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setSurvol(true); }}
      onDragLeave={() => setSurvol(false)}
      onDrop={(e) => {
        e.preventDefault();
        setSurvol(false);
        deposer(e.dataTransfer.files);
      }}
      style={{
        padding: "10px 14px", borderBottom: "1px solid var(--line)",
        background: survol ? "var(--accent-soft)" : "var(--bg-panel-alt)",
        borderTop: survol ? "2px dashed var(--accent)" : "2px dashed transparent",
        display: "flex", alignItems: "center", gap: 10, fontSize: 12.5,
      }}
    >
      {enCours > 0
        ? <Loader2 size={14} className="rotation" color="var(--accent)" />
        : <Upload size={14} color="var(--ink-faint)" />}
      <span style={{ color: "var(--ink-faint)" }}>
        {enCours > 0 ? `Envoi en cours (${enCours})…` : <>{invitation}, ou </>}
        {enCours === 0 && (
          <button
            onClick={() => champFichier.current?.click()}
            style={{ border: "none", background: "transparent", color: "var(--accent)",
                     fontSize: 12.5, padding: 0, cursor: "pointer" }}
          >
            parcourez vos fichiers
          </button>
        )}
      </span>
      {/* Ce qui doit être décidé **avant** de déposer, quand il y a un choix à
          faire — pas une option cachée dans un menu qu'on ouvre après coup. */}
      {enCours === 0 && complement}
      {message && (
        <span style={{ color: message.ton === "ok" ? "var(--ink)" : "var(--brick)" }}>
          {t(message.texte)}
        </span>
      )}
      <input
        ref={champFichier}
        type="file"
        multiple={multiple}
        aria-label={ariaLabel}
        style={{ display: "none" }}
        onChange={(e) => { deposer(e.target.files); e.target.value = ""; }}
      />
    </div>
  );
}
