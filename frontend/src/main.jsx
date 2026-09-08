import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthContext.jsx";
import BarriereErreur from "./components/BarriereErreur.jsx";
import "./index.css";
import { t } from "./lib/langue";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* Dernière barrière : ce qui casse en dehors d'un écran — la reprise de
        session, la page de connexion — laisse malgré tout de quoi comprendre et
        recharger, plutôt qu'une page blanche. */}
    <BarriereErreur titre={t("L'application s'est interrompue")}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BarriereErreur>
  </React.StrictMode>
);
