import React, { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";

const AuthCallback = () => {
  const navigate = useNavigate();

  useEffect(() => {
    navigate("/upload", { replace: true });
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="backdrop-blur-2xl bg-white/10 rounded-3xl border border-white/20 shadow-2xl p-8 sm:p-10 max-w-md w-full text-center">
        <Loader2 className="w-10 h-10 text-purple-400 animate-spin mx-auto mb-4" />
        <p className="text-purple-200">Redirecting...</p>
      </div>
    </div>
  );
};

export default AuthCallback;
