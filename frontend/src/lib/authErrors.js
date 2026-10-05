const AUTH_ERROR_COPY = {
  "auth/email-already-in-use": {
    title: "Account already exists",
    message: "An account already exists for this email. Sign in instead.",
    action: "signIn",
    actionLabel: "Sign in instead",
  },
  "auth/user-not-found": {
    title: "No account found",
    message: "We could not find an account for this email. Create one first.",
    action: "signUp",
    actionLabel: "Create account",
  },
  "auth/wrong-password": {
    title: "Incorrect password",
    message: "The password is not correct. Try again or create an account.",
  },
  "auth/invalid-credential": {
    title: "Sign-in failed",
    message: "Email or password is incorrect. Please try again.",
  },
  "auth/invalid-email": {
    title: "Invalid email",
    message: "Enter a complete email address such as you@example.com.",
  },
  "auth/weak-password": {
    title: "Weak password",
    message: "Use at least 6 characters for your password.",
  },
  "auth/too-many-requests": {
    title: "Too many attempts",
    message: "Please wait a few minutes before trying again.",
  },
  "auth/popup-closed-by-user": {
    title: "Google sign-in cancelled",
    message: "Google sign-in was closed before it finished. Please try again.",
  },
  "auth/operation-not-allowed": {
    title: "Google sign-in is unavailable",
    message: "Google sign-in has not been configured for this environment yet.",
  },
  "auth/unauthorized-domain": {
    title: "Domain not allowed",
    message:
      "This site URL is not authorized in Firebase. Add localhost (or 127.0.0.1) under Authentication → Settings → Authorized domains.",
  },
  "auth/invalid-api-key": {
    title: "Invalid Firebase API key",
    message:
      "VITE_FIREBASE_API_KEY is wrong or revoked. Copy the Web API key from Firebase Console → Project settings → Your apps, then update frontend/.env and restart npm run dev.",
  },
  "auth/api-key-not-valid.-please-pass-a-valid-api-key.": {
    title: "Invalid Firebase API key",
    message:
      "VITE_FIREBASE_API_KEY is wrong or revoked. Copy the Web API key from Firebase Console → Project settings → Your apps, then update frontend/.env and restart npm run dev.",
  },
};

export function getAuthErrorName(error) {
  const value = error?.code || error?.name || "";
  return String(value);
}

export function normalizeAuthError(error, options = {}) {
  const code = getAuthErrorName(error) || "AuthError";
  const rawMessage = String(error?.message || "");

  if (/network|failed to fetch|load failed/i.test(rawMessage)) {
    return {
      code: "NetworkError",
      title: "Connection problem",
      message: "Check your internet connection and try again.",
    };
  }

  if (
    /api key not valid|invalid-api-key|API_KEY_INVALID/i.test(rawMessage) ||
    /Unsafe attempt to load URL.*firebaseapp\.com/i.test(rawMessage)
  ) {
    return {
      code: "auth/invalid-api-key",
      title: "Invalid Firebase API key",
      message:
        "Your Firebase Web API key is missing, revoked, or restricted. In Firebase Console → Project settings → Your apps, copy apiKey into VITE_FIREBASE_API_KEY (and Vercel env vars), then restart the dev server.",
    };
  }

  const configured = AUTH_ERROR_COPY[code];
  if (configured) {
    return { code, ...configured };
  }

  return {
    code,
    title: options.fallbackTitle || "Authentication failed",
    message:
      options.fallbackMessage ||
      "We could not complete that authentication request. Please try again.",
  };
}
