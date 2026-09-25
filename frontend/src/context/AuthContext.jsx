import React, {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "firebase/auth";
import { auth, googleProvider, firebaseConfigStatus } from "../lib/firebaseClient";
import { normalizeAuthError } from "../lib/authErrors";
import { AuthContextValue } from "./authContextValue";

function mapFirebaseUser(firebaseUser) {
  if (!firebaseUser) return null;
  return {
    id: firebaseUser.uid,
    username: firebaseUser.email || firebaseUser.displayName || firebaseUser.uid,
    email: firebaseUser.email || "",
    attributes: {
      email: firebaseUser.email,
      name: firebaseUser.displayName,
    },
  };
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = useCallback(async () => {
    const current = auth.currentUser;
    const mapped = mapFirebaseUser(current);
    setUser(mapped);
    setLoading(false);
    return mapped;
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(mapFirebaseUser(firebaseUser));
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const signInWithEmail = async (rawEmail, rawPassword) => {
    const email = rawEmail.trim().toLowerCase();
    const password = rawPassword;
    try {
      await signInWithEmailAndPassword(auth, email, password);
      await refreshUser();
      return { data: { session: true }, error: null };
    } catch (error) {
      return { data: null, error: normalizeAuthError(error) };
    }
  };

  const signUpWithEmail = async (rawEmail, rawPassword) => {
    const email = rawEmail.trim().toLowerCase();
    const password = rawPassword;
    try {
      await createUserWithEmailAndPassword(auth, email, password);
      await refreshUser();
      return { data: { session: true }, error: null };
    } catch (error) {
      return { data: null, error: normalizeAuthError(error) };
    }
  };

  const signInWithGoogle = async () => {
    if (!firebaseConfigStatus.googleEnabled) {
      return {
        data: null,
        error: normalizeAuthError({ code: "auth/operation-not-allowed" }),
      };
    }

    try {
      await signInWithPopup(auth, googleProvider);
      await refreshUser();
      return { data: { session: true }, error: null };
    } catch (error) {
      return {
        data: null,
        error: normalizeAuthError(error, {
          fallbackTitle: "Google sign-in failed",
          fallbackMessage: "We could not complete Google sign-in. Please try again.",
        }),
      };
    }
  };

  const logout = async () => {
    await signOut(auth);
    setUser(null);
  };

  const value = {
    user,
    loading,
    signInWithEmail,
    signUpWithEmail,
    signInWithGoogle,
    googleEnabled: firebaseConfigStatus.googleEnabled,
    logout,
    refreshUser,
  };

  return (
    <AuthContextValue.Provider value={value}>
      {!loading && children}
    </AuthContextValue.Provider>
  );
};
