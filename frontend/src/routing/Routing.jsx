// src/routing/Routing.jsx
import React, { Suspense, lazy } from "react";
import { Routes, Route, useLocation } from "react-router-dom";

// Layout components
import Navbar from "../layout/Header";
import Footer from "../layout/Footer";
import ScrollToTop from "../components/ScrollonTop";
import DocumentationPage from "../pages/Documentation";

import HomePage from "../pages/Home";
import UploadPage from "../pages/Upload";
import ProtectedRoute from "../components/auth/ProtectedRoute";
import NotFoundPage from "../pages/NotFound";
// Lazy-loaded pages
const ContactPage = lazy(() => import("../pages/Contact"));

const LoginPage = lazy(() => import("../pages/Login"));

// Layout Wrapper
const Layout = ({ children }) => {
  const location = useLocation();

  const hideLayoutRoutes = ["/login", "/signup"];
  const hideLayout = hideLayoutRoutes.includes(location.pathname);

  return (
    <>
      {!hideLayout && <Navbar />}
      {children}
      {!hideLayout && <Footer />}
    </>
  );
};

const Routing = () => {
  return (
    <>
      <ScrollToTop />

      <Routes>
        {/* HOME — NO SUSPENSE */}
        <Route
          path="/"
          element={
            <Layout>
              <HomePage />
            </Layout>
          }
        />

        {/* OTHER PAGES — SUSPENSE OK */}
        <Route
          path="/upload"
          element={
            <Suspense fallback={null}>
              <ProtectedRoute>
                <Layout>
                  <UploadPage />
                </Layout>
              </ProtectedRoute>
            </Suspense>
          }
        />

        <Route
          path="/contact"
          element={
            <Suspense fallback={null}>
              <Layout>
                <ContactPage />
              </Layout>
            </Suspense>
          }
        />

        <Route
          path="/docs"
          element={
            <Layout>
              <DocumentationPage />
            </Layout>
          }
        />

        <Route
          path="/login"
          element={
            <Suspense fallback={null}>
              <LoginPage />
            </Suspense>
          }
        />

        {/* 404 - CATCH ALL */}
        <Route
          path="*"
          element={
            <Layout>
              <NotFoundPage />
            </Layout>
          }
        />
      </Routes>
    </>
  );
};

export default Routing;
