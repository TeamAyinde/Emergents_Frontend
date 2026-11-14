import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";
import { Platform } from "react-native";

import { api, SignUpBody, tokenStore, User } from "./api";

WebBrowser.maybeCompleteAuthSession();

const AUTH_URL = "https://auth.emergentagent.com/?redirect=";
const sentSessionIds = new Set<string>();

function sessionIdFrom(url: string | null | undefined): string | null {
  // Stripe also returns a session_id to /payment-result — that one is not a Google login
  if (!url || url.includes("payment-result")) return null;
  const m = url?.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

function cleanWebUrl() {
  const url = new URL(window.location.href);
  url.searchParams.delete("session_id");
  const hash = url.hash.replace(/^#/, "").split("&").filter((p) => p && !p.startsWith("session_id=")).join("&");
  url.hash = hash ? `#${hash}` : "";
  window.history.replaceState(window.history.state, "", url.toString());
}

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (body: SignUpBody) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  /** Exchanges a one-time Google session_id (once) for our own token. */
  const exchange = useCallback(async (sessionId: string) => {
    if (sentSessionIds.has(sessionId)) return false;
    sentSessionIds.add(sessionId);
    const res = await api.googleSession(sessionId);
    await tokenStore.setItem(res.access_token);
    setUser(res.user);
    return true;
  }, []);

  const bootstrap = useCallback(async () => {
    try {
      const pending =
        Platform.OS === "web" ? sessionIdFrom(window.location.href) : sessionIdFrom(await Linking.getInitialURL());
      if (pending) {
        try {
          if (await exchange(pending)) {
            if (Platform.OS === "web") cleanWebUrl();
            return;
          }
        } catch {}
      }
      const token = await tokenStore.getItem();
      if (!token) {
        setUser(null);
        return;
      }
      const me = await api.me();
      setUser(me);
    } catch {
      await tokenStore.remove();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [exchange]);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // Hot deep links on phones (Android may deliver the Google callback here)
  useEffect(() => {
    if (Platform.OS === "web") return;
    const sub = Linking.addEventListener("url", ({ url }) => {
      const sid = sessionIdFrom(url);
      if (sid) exchange(sid).catch(() => {});
    });
    return () => sub.remove();
  }, [exchange]);

  const signInWithGoogle = useCallback(async () => {
    if (Platform.OS === "web") {
      window.location.href = AUTH_URL + encodeURIComponent(window.location.origin + "/");
      return;
    }
    const redirect = Linking.createURL("");
    let captured: string | null = null;
    const sub = Linking.addEventListener("url", ({ url }) => {
      captured = url;
    });
    try {
      const result = await WebBrowser.openAuthSessionAsync(AUTH_URL + encodeURIComponent(redirect), redirect);
      const url = (result.type === "success" ? result.url : null) ?? captured ?? (await Linking.getInitialURL());
      const sid = sessionIdFrom(url);
      if (!sid) {
        if (result.type === "cancel" || result.type === "dismiss") return;
        throw new Error("Google sign-in failed — try again");
      }
      await exchange(sid);
    } finally {
      sub.remove();
    }
  }, [exchange]);

  const signIn = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    await tokenStore.setItem(res.access_token);
    setUser(res.user);
  }, []);

  const signUp = useCallback<AuthContextValue["signUp"]>(async (body) => {
    const res = await api.register(body);
    await tokenStore.setItem(res.access_token);
    setUser(res.user);
  }, []);

  const signOut = useCallback(async () => {
    await tokenStore.remove();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {}
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn, signUp, signInWithGoogle, signOut, refresh }),
    [user, loading, signIn, signUp, signInWithGoogle, signOut, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
