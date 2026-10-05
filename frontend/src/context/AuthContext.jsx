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
  signInWithRedirect,
  signOut,
} from "firebase/auth";
import {
  auth,
  getGoogleRedirectResultOnce,
  googleProvider,
  firebaseConfigStatus,
} from "../lib/firebaseClient";
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

const POPUP_FALLBACK_CODES = new Set([
  "auth/popup-blocked",
  "auth/cancelled-popup-request",
]);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [googleRedirectError, setGoogleRedirectError] = useState(null);

  const refreshUser = useCallback(async () => {
    const mapped = mapFirebaseUser(auth.currentUser);
    setUser(mapped);
    return mapped;
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(mapFirebaseUser(firebaseUser));
      setLoading(false);
    });

    void getGoogleRedirectResultOnce()
      .then((result) => {
        if (result?.user) {
          setUser(mapFirebaseUser(result.user));
        }
      })
      .catch((error) => {
        if (auth.currentUser) {
          setUser(mapFirebaseUser(auth.currentUser));
          return;
        }
        setGoogleRedirectError(
          normalizeAuthError(error, {
            fallbackTitle: "Google sign-in failed",
            fallbackMessage:
              "We could not complete Google sign-in. Please try again.",
          }),
        );
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
      const code = String(error?.code || "");
      if (POPUP_FALLBACK_CODES.has(code)) {
        try {
          await signInWithRedirect(auth, googleProvider);
          return { data: null, error: null, redirecting: true };
        } catch (redirectError) {
          return {
            data: null,
            error: normalizeAuthError(redirectError, {
              fallbackTitle: "Google sign-in failed",
              fallbackMessage:
                "We could not complete Google sign-in. Please try again.",
            }),
          };
        }
      }

      if (code === "auth/popup-closed-by-user") {
        return {
          data: null,
          error: normalizeAuthError(error),
        };
      }

      return {
        data: null,
        error: normalizeAuthError(error, {
          fallbackTitle: "Google sign-in failed",
          fallbackMessage:
            "We could not complete Google sign-in. Please try again.",
        }),
      };
    }
  };

  const logout = async () => {
    await signOut(auth);
    setUser(null);
  };

  const clearGoogleRedirectError = useCallback(() => {
    setGoogleRedirectError(null);
  }, []);

  const value = {
    user,
    loading,
    googleRedirectError,
    clearGoogleRedirectError,
    signInWithEmail,
    signUpWithEmail,
    signInWithGoogle,
    googleEnabled: firebaseConfigStatus.googleEnabled,
    logout,
    refreshUser,
  };

  return (
    <AuthContextValue.Provider value={value}>
      {children}
    </AuthContextValue.Provider>
  );
};
