import React, { useEffect, useState } from "react";
import { useAuth } from "../context/useAuth";
import { useNavigate, useLocation } from "react-router-dom";
import {
  AlertCircle,
  Loader2,
  Lock,
  Mail,
  Shield,
  X,
} from "lucide-react";
import { showToast } from "../utils/toast";

function resolveRedirect(value) {
  const pathname = typeof value === "string" ? value : value?.pathname;
  if (
    typeof pathname !== "string" ||
    !pathname.startsWith("/") ||
    pathname.startsWith("//")
  ) {
    return null;
  }

  const search =
    typeof value?.search === "string" && value.search.startsWith("?")
      ? value.search
      : "";
  return `${pathname}${search}`;
}

function readSavedRedirect() {
  try {
    const saved = sessionStorage.getItem("auth_redirect");
    return saved ? JSON.parse(saved) : null;
  } catch {
    sessionStorage.removeItem("auth_redirect");
    return null;
  }
}

function createUiError(title, message) {
  return { title, message };
}

const AuthAlert = ({ error, onAction, onDismiss }) => {
  if (!error) return null;

  return (
    <div
      id="auth-error"
      role="alert"
      aria-live="assertive"
      className="rounded-xl border border-red-400/30 bg-red-500/15 p-4 text-left backdrop-blur-sm"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-300" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-red-100">
            {error.title || "Authentication failed"}
          </p>
          <p className="mt-1 text-sm leading-5 text-red-200/90">
            {error.message}
          </p>
          {error.action && error.actionLabel && (
            <button
              type="button"
              onClick={() => onAction(error.action)}
              className="mt-3 text-sm font-semibold text-white underline decoration-red-300/60 underline-offset-4 hover:decoration-white"
            >
              {error.actionLabel}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss authentication error"
          className="rounded-lg p-1 text-red-200/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

const Login = () => {
  const {
    user,
    loading: authLoading,
    signInWithEmail,
    signUpWithEmail,
    signInWithGoogle,
    googleEnabled,
    googleRedirectError,
    clearGoogleRedirectError,
  } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [authMode, setAuthMode] = useState("signIn");
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);

  const from =
    resolveRedirect(location.state?.from) ||
    resolveRedirect(readSavedRedirect()) ||
    "/upload";

  useEffect(() => {
    if (authLoading || !user) return;
    sessionStorage.removeItem("auth_redirect");
    navigate(from, { replace: true });
  }, [authLoading, user, from, navigate]);

  useEffect(() => {
    if (!googleRedirectError || user) return;
    setError(googleRedirectError);
    clearGoogleRedirectError();
  }, [googleRedirectError, clearGoogleRedirectError, user]);

  const changeAuthMode = (nextMode) => {
    setAuthMode(nextMode);
    setError(null);
    setPassword("");
  };

  const handleAuthErrorAction = (nextMode) => {
    changeAuthMode(nextMode);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email) {
      setError(createUiError("Email required", "Enter your email to continue."));
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
      setError(
        createUiError(
          "Invalid email",
          "Enter a complete email address such as you@example.com.",
        ),
      );
      return;
    }

    if (!password || password.length < 6) {
      setError(
        createUiError(
          "Password required",
          "Use at least 6 characters for your password.",
        ),
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const { data, error: authError } =
        authMode === "signIn"
          ? await signInWithEmail(email, password)
          : await signUpWithEmail(email, password);

      if (authError) {
        setError(authError);
        return;
      }

      if (data?.session) {
        showToast.success(
          authMode === "signIn" ? "Signed in successfully." : "Account created.",
        );
      }
    } catch (err) {
      setError(
        createUiError(
          "Authentication failed",
          err?.message || "Please try again in a moment.",
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    let redirecting = false;
    try {
      setLoading(true);
      setError(null);

      const [pathname, query = ""] = from.split("?", 2);
      sessionStorage.setItem(
        "auth_redirect",
        JSON.stringify({
          pathname,
          search: query ? `?${query}` : "",
          state: null,
        }),
      );

      const { data, error: authError, redirecting: isRedirecting } =
        await signInWithGoogle();

      if (isRedirecting) {
        redirecting = true;
        return;
      }

      if (authError) {
        setError(authError);
        return;
      }

      if (data?.session) {
        showToast.success("Signed in with Google.");
      }
    } catch (err) {
      setError(
        createUiError(
          "Google sign-in failed",
          err?.message || "Please try again.",
        ),
      );
    } finally {
      if (!redirecting) {
        setLoading(false);
      }
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <Loader2 className="h-10 w-10 animate-spin text-purple-400" aria-label="Loading session" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
      <div className="relative mt-10 z-10 w-full max-w-md">
        <div className="backdrop-blur-2xl bg-white/10 rounded-3xl border border-white/20 shadow-2xl p-8 sm:p-10">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-purple-500 to-indigo-600 mb-4 shadow-lg">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white mb-2">
              {authMode === "signIn" ? "Welcome back" : "Create your account"}
            </h1>
            <p className="text-md font-semibold text-purple-400/80">
              {authMode === "signIn"
                ? "Sign in to continue to Manhwa AI"
                : "Start creating with Manhwa AI"}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div
              role="tablist"
              aria-label="Choose sign in or account creation"
              className="grid grid-cols-2 rounded-xl border border-white/15 bg-black/15 p-1"
            >
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "signIn"}
                onClick={() => changeAuthMode("signIn")}
                disabled={loading}
                className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${
                  authMode === "signIn"
                    ? "bg-white/15 text-white shadow-sm"
                    : "text-purple-200/70 hover:text-white"
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "signUp"}
                onClick={() => changeAuthMode("signUp")}
                disabled={loading}
                className={`rounded-lg px-3 py-2.5 text-sm font-semibold transition-all ${
                  authMode === "signUp"
                    ? "bg-white/15 text-white shadow-sm"
                    : "text-purple-200/70 hover:text-white"
                }`}
              >
                Create account
              </button>
            </div>

            {googleEnabled && (
              <>
                <button
                  type="button"
                  onClick={handleGoogleSignIn}
                  disabled={loading}
                  className="w-full py-3.5 px-4 rounded-xl bg-transparent border border-gray-400/50 hover:bg-white/10 text-white font-semibold flex items-center justify-center gap-3 transition-all shadow-lg hover:shadow-xl disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? "Connecting..." : "Continue with Google"}
                </button>

                <div className="flex items-center gap-4">
                  <div className="flex-1 h-px bg-white/10" />
                  <span className="text-xs text-white font-medium">OR</span>
                  <div className="flex-1 h-px bg-white/20" />
                </div>
              </>
            )}

            <div className="space-y-2">
              <label className="text-sm font-medium text-white block">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-purple-300 w-5 h-5" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setError(null);
                  }}
                  placeholder="you@example.com"
                  className="w-full rounded-xl bg-transparent backdrop-blur-sm border border-white/20 py-3.5 pl-12 pr-4 text-white placeholder-gray-300/50 focus:outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-400/30 transition-all"
                  autoFocus
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium text-white block">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-purple-300 w-5 h-5" />
                <input
                  type="password"
                  required
                  minLength={6}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError(null);
                  }}
                  placeholder="At least 6 characters"
                  className="w-full rounded-xl bg-transparent backdrop-blur-sm border border-white/20 py-3.5 pl-12 pr-4 text-white placeholder-gray-300/50 focus:outline-none focus:border-purple-400 focus:ring-2 focus:ring-purple-400/30 transition-all"
                />
              </div>
            </div>

            <AuthAlert
              error={error}
              onAction={handleAuthErrorAction}
              onDismiss={() => setError(null)}
            />

            <button
              type="submit"
              disabled={loading || !email || !password}
              className="w-full py-3.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-bold shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Please wait...
                </>
              ) : authMode === "signIn" ? (
                "Sign in"
              ) : (
                "Create account"
              )}
            </button>
          </form>
        </div>

        <div className="text-center mt-7 space-y-2">
          <div className="flex items-center mb-5 justify-center gap-2 text-sm text-gray-400">
            <Lock className="w-4 h-4" />
            <span>Secured by Firebase Authentication</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
