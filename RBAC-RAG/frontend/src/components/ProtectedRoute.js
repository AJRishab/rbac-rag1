import React, { useMemo } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

export function ProtectedRoute({ children, requireAdmin = false }) {
  const { user, initializing } = useAuth();
  const location = useLocation();

  // Extracted so the object identity is stable across renders — avoids
  // unnecessary re-renders of `<Navigate>` children.
  const loginRedirectState = useMemo(() => ({ from: location }), [location]);

  if (initializing) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="mono-label text-slate-400">Initializing…</div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace state={loginRedirectState} />;
  if (user.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  if (user.status !== 'approved' && location.pathname !== '/pending' && location.pathname !== '/change-password') {
    return <Navigate to="/pending" replace />;
  }
  if (requireAdmin && user.role !== 'admin') {
    return <Navigate to="/chat" replace />;
  }
  return children;
}
