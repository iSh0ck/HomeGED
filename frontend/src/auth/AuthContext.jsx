import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setUnauthorizedHandler } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [chargement, setChargement] = useState(true);

  const rafraichir = useCallback(async () => {
    // Le jeton n'est plus lisible par la page : on ne peut plus deviner si une
    // session existe, on le demande à l'API — un 401 signifie « non connecté ».
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setChargement(false);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    rafraichir();
  }, [rafraichir]);

  /**
   * Première étape. Rend `{ otpRequis, jetonIntermediaire }` quand le compte
   * porte une double authentification : la session n'est alors pas ouverte, et
   * c'est à l'appelant de demander le code puis d'appeler `validerOtp`.
   */
  async function login(email, motDePasse) {
    const reponse = await api.login(email, motDePasse);
    if (reponse?.otp_requis) {
      return { otpRequis: true, jetonIntermediaire: reponse.jeton_intermediaire };
    }
    await rafraichir();
    return { otpRequis: false };
  }

  async function validerOtp(jetonIntermediaire, code) {
    await api.verifierOtp(jetonIntermediaire, code);
    await rafraichir();
  }

  async function logout() {
    await api.logout().catch(() => {});
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, chargement, login, validerOtp, logout, rafraichir }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
