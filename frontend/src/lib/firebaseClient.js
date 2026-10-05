import { initializeApp } from "firebase/app";
import { getAuth, getRedirectResult, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

const requiredKeys = [
  "VITE_FIREBASE_API_KEY",
  "VITE_FIREBASE_AUTH_DOMAIN",
  "VITE_FIREBASE_PROJECT_ID",
  "VITE_FIREBASE_APP_ID",
];

const missing = requiredKeys.filter((key) => !import.meta.env[key]);
if (missing.length > 0) {
  console.warn(
    `Firebase is not fully configured. Missing: ${missing.join(", ")}`,
  );
}

export const firebaseApp = initializeApp(firebaseConfig);
export const auth = getAuth(firebaseApp);
export const googleProvider = new GoogleAuthProvider();
googleProvider.addScope("email");
googleProvider.addScope("profile");
googleProvider.setCustomParameters({ prompt: "select_account" });

/** React Strict Mode mounts twice; getRedirectResult must run only once per page load. */
let googleRedirectResultPromise = null;

export function getGoogleRedirectResultOnce() {
  if (!googleRedirectResultPromise) {
    googleRedirectResultPromise = getRedirectResult(auth);
  }
  return googleRedirectResultPromise;
}

export const firebaseConfigStatus = {
  googleEnabled: Boolean(
    import.meta.env.VITE_FIREBASE_API_KEY &&
      import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  ),
};

async function warnIfFirebaseApiKeyInvalid() {
  if (!import.meta.env.DEV) return;
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
  if (!apiKey) return;

  try {
    const response = await fetch(
      `https://www.googleapis.com/identitytoolkit/v3/relyingparty/getProjectConfig?key=${encodeURIComponent(apiKey)}`,
    );
    if (response.ok) return;

    const body = await response.json().catch(() => null);
    const reason = body?.error?.details?.[0]?.reason || body?.error?.message;
    if (reason === "API_KEY_INVALID" || /not valid/i.test(body?.error?.message || "")) {
      console.error(
        "[Firebase] VITE_FIREBASE_API_KEY is invalid for Identity Toolkit. " +
          "Copy the Web app apiKey from Firebase Console → Project settings → Your apps, " +
          "update frontend/.env, and restart `npm run dev`.",
      );
    }
  } catch {
    // Ignore network errors during dev sanity check.
  }
}

warnIfFirebaseApiKeyInvalid();
