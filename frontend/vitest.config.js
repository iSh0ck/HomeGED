import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Tests de rendu du frontend.
 *
 * Le projet n'en avait aucun : la seule vérification possible était de cliquer
 * dans l'application, ce qui n'a pas eu lieu à chaque changement. Un composant
 * qui ne se monte plus — un import oublié, une API de React qui change de
 * version majeure — n'apparaissait qu'à l'écran de l'utilisateur.
 *
 * L'ambition reste modeste et assumée : vérifier que les écrans se montent et
 * que les composants de saisie répondent aux gestes qu'on attend d'eux. Ce
 * n'est pas un test d'apparence — l'alignement et les couleurs continuent de
 * demander un œil humain.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    // `.js` **et** `.jsx` : le motif d'origine ne prenait que le second, si bien
    // qu'un fichier de tests écrit en `.js` était ignoré sans un mot. Deux
    // fichiers l'ont été — on croyait leurs vérifications acquises.
    include: ["src/**/*.test.{js,jsx}"],
    setupFiles: ["./src/tests/preparation.js"],
  },
});
