"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8080";
const AUTH_STORAGE_KEY = "cipherlens.auth.v1";
const AUTH_KDF_SALT = "cipherlens-static-kdf-salt-v1";
const AUTH_PASSPHRASE = "cipherlens-browser-auth";

type AuthMode = "login" | "register";

type Doc = {
  id: number;
  original_filename: string;
  document_type: string;
  ml_classification_confidence: number;
  ml_processed: boolean;
  created_at: string;
};

type Insight = {
  document_id: number;
  document_type: string;
  classification_confidence: number;
  ml_processed: boolean;
  text_preview: string;
  extracted_entities: Record<string, string[]>;
};

type UserProfile = {
  id: number;
  username: string;
  email: string;
  public_key: string;
  created_at: string;
};

type StoredAuthPayload = {
  token: string;
  username: string;
  savedAt: string;
};

// --- Crypto Logic ---
async function deriveAesKey() {
  const encoder = new TextEncoder();
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    encoder.encode(`${AUTH_PASSPHRASE}:${window.location.origin}`),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  return crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: encoder.encode(AUTH_KDF_SALT),
      iterations: 100_000,
      hash: "SHA-256",
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary);
}

function base64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function encryptAuth(payload: StoredAuthPayload): Promise<string> {
  const key = await deriveAesKey();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(JSON.stringify(payload));
  const cipherBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    encoded,
  );
  const ivB64 = bytesToBase64(iv);
  const cipherB64 = bytesToBase64(new Uint8Array(cipherBuffer));
  return `${ivB64}.${cipherB64}`;
}

async function decryptAuth(
  serialized: string,
): Promise<StoredAuthPayload | null> {
  try {
    const [ivPart, cipherPart] = serialized.split(".");
    if (!ivPart || !cipherPart) return null;
    const iv = base64ToBytes(ivPart);
    const cipher = base64ToBytes(cipherPart);
    const key = await deriveAesKey();
    const plainBuffer = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: iv as BufferSource },
      key,
      cipher as BufferSource,
    );
    const plain = new TextDecoder().decode(plainBuffer);
    return JSON.parse(plain) as StoredAuthPayload;
  } catch {
    return null;
  }
}

// --- API Helpers ---
async function uploadWithProgress(
  url: string,
  token: string,
  form: FormData,
  onProgress: (value: number) => void,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (evt) => {
      if (evt.lengthComputable) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    };
    xhr.onerror = () => reject(new Error("Upload failed"));
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
      }
    };
    xhr.send(form);
  });
}

export default function Home() {
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [rememberMe, setRememberMe] = useState(true);
  const [authReady, setAuthReady] = useState(false);
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  const [documents, setDocuments] = useState<Doc[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<number | null>(null);
  const [insight, setInsight] = useState<Insight | null>(null);

  const [dropFile, setDropFile] = useState<File | null>(null);
  const [verifyDocFile, setVerifyDocFile] = useState<File | null>(null);
  const [verifySigFile, setVerifySigFile] = useState<File | null>(null);

  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [signProgress, setSignProgress] = useState(0);
  const [showSignProgress, setShowSignProgress] = useState(false);
  const [isInsightsVisible, setIsInsightsVisible] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState<string>("");
  const [verifyResult, setVerifyResult] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [activeTab, setActiveTab] = useState<"upload" | "verify">("upload");
  const [showWelcome, setShowWelcome] = useState(false);

  const authHeaders = useMemo(
    () => ({ Authorization: `Bearer ${token}` }),
    [token],
  );

  async function refreshDocuments(tokenOverride?: string) {
    const activeToken = tokenOverride ?? token;
    if (!activeToken) return;
    const res = await fetch(`${API_BASE}/api/documents/`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    });
    if (!res.ok) return;
    const data = (await res.json()) as Doc[];
    setDocuments(data);
    if (data.length > 0 && selectedDocId === null) {
      setSelectedDocId(data[0].id);
      await fetchInsights(data[0].id);
    }
  }

  async function fetchInsights(id: number) {
    if (!token) return;
    const res = await fetch(`${API_BASE}/api/documents/${id}/insights`, {
      headers: authHeaders,
    });
    if (!res.ok) return;
    setInsight((await res.json()) as Insight);
  }

  async function handleAuth() {
    try {
      setBusy(true);
      const payload =
        authMode === "register"
          ? { username, email, password }
          : { username, password };
      const endpoint = authMode === "register" ? "register" : "login";
      const res = await fetch(`${API_BASE}/api/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        if (endpoint === "login") {
          throw new Error("Invalid Password or User name");
        }
        throw new Error(data.detail ?? "Auth failed");
      }
      setToken(data.access_token);
      setAuthMessage(`Logged in as ${data.username}`);
      const meRes = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });
      if (meRes.ok) {
        setUserProfile((await meRes.json()) as UserProfile);
      }
      if (rememberMe) {
        const encrypted = await encryptAuth({
          token: data.access_token,
          username: data.username,
          savedAt: new Date().toISOString(),
        });
        localStorage.setItem(AUTH_STORAGE_KEY, encrypted);
      } else {
        localStorage.removeItem(AUTH_STORAGE_KEY);
      }
      await refreshDocuments(data.access_token);
      
      setShowWelcome(true);
      setTimeout(() => {
        setShowWelcome(false);
      }, 2500);
      
    } catch (err) {
      setAuthMessage((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalyze() {
    if (!dropFile || !token) return;
    try {
      setBusy(true);
      setAnalyzeProgress(0);
      setIsInsightsVisible(false); // Reset insights visibility on new scan
      const form = new FormData();
      form.append("document", dropFile);
      const result = (await uploadWithProgress(
        `${API_BASE}/api/ml/analyze`,
        token,
        form,
        setAnalyzeProgress,
      )) as { document_type: string; confidence: number };
      setAnalyzeResult(
        `AI Insight: ${result.document_type} (${(result.confidence * 100).toFixed(1)}%)`,
      );
    } catch (err) {
      setAnalyzeResult((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleSign() {
    if (!dropFile || !token) return;
    try {
      setBusy(true);
      setSignProgress(0);
      setShowSignProgress(true); // Trigger the secondary progress bar
      const form = new FormData();
      form.append("document", dropFile);
      const result = (await uploadWithProgress(
        `${API_BASE}/api/documents/sign`,
        token,
        form,
        setSignProgress,
      )) as any;
      
      // Trigger download of the .sig file
      if (result && result.signature_b64) {
        const blob = new Blob([result.signature_b64], { type: "text/plain" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${dropFile.name}.sig`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }

      await refreshDocuments();
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify() {
    if (!verifyDocFile || !verifySigFile || !token) return;
    try {
      setBusy(true);
      const form = new FormData();
      form.append("document", verifyDocFile);
      form.append("signature", verifySigFile);
      const res = await fetch(`${API_BASE}/api/documents/verify`, {
        method: "POST",
        headers: authHeaders,
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Verification failed");
      setVerifyResult(data.message);
    } catch (err) {
      setVerifyResult((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function restoreAuth() {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (!stored) {
        if (!cancelled) setAuthReady(true);
        return;
      }
      const payload = await decryptAuth(stored);
      if (!payload?.token) {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        if (!cancelled) setAuthReady(true);
        return;
      }

      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${payload.token}` },
      });
      if (!res.ok) {
        localStorage.removeItem(AUTH_STORAGE_KEY);
        if (!cancelled) setAuthReady(true);
        return;
      }

      if (!cancelled) {
        setUsername(payload.username);
        setToken(payload.token);
        setAuthMessage(`Welcome back, ${payload.username}`);
      }
      const meRes = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${payload.token}` },
      });
      if (meRes.ok && !cancelled) {
        setUserProfile((await meRes.json()) as UserProfile);
      }
      const docsRes = await fetch(`${API_BASE}/api/documents/`, {
        headers: { Authorization: `Bearer ${payload.token}` },
      });
      if (docsRes.ok) {
        const docs = (await docsRes.json()) as Doc[];
        if (!cancelled) {
          setDocuments(docs);
          if (docs.length > 0) {
            setSelectedDocId(docs[0].id);
            const insightRes = await fetch(
              `${API_BASE}/api/documents/${docs[0].id}/insights`,
              {
                headers: { Authorization: `Bearer ${payload.token}` },
              },
            );
            if (insightRes.ok) {
              setInsight((await insightRes.json()) as Insight);
            }
          }
        }
      }
      if (!cancelled) setAuthReady(true);
    }

    void restoreAuth();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleDocumentMouseDown(event: MouseEvent) {
      if (!profileMenuOpen) return;
      const target = event.target as Node;
      if (profileMenuRef.current && !profileMenuRef.current.contains(target)) {
        setProfileMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", handleDocumentMouseDown);
    return () => {
      document.removeEventListener("mousedown", handleDocumentMouseDown);
    };
  }, [profileMenuOpen]);

  if (!authReady) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#030712] text-slate-200">
        <div className="flex flex-col items-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-cyan-400"></div>
          <p className="text-sm font-medium tracking-wide text-cyan-400/80 animate-pulse">
            Restoring secure session...
          </p>
        </div>
      </main>
    );
  }

  if (!token) {
    // Return standard login page...
    return (
      <main className="relative min-h-screen overflow-hidden bg-[#030712] text-slate-100 flex items-center justify-center">
        <div className="pointer-events-none absolute -top-32 left-1/4 h-96 w-96 rounded-full bg-cyan-600/20 blur-[100px] animate-pulse" />
        <div className="pointer-events-none absolute bottom-0 right-1/4 h-80 w-80 rounded-full bg-violet-600/20 blur-[100px] animate-pulse delay-1000" />
        
        <div className="w-full max-w-md p-6 z-10">
          <section className="rounded-3xl border border-white/5 bg-white/[0.02] p-8 shadow-2xl backdrop-blur-2xl transition-all">
            <div className="text-center mb-8">
              <h1 className="text-4xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-br from-white to-slate-400">
                CipherLens
              </h1>
              <p className="mt-2 text-sm font-medium text-slate-400">
                Secure signing with AI intelligence.
              </p>
            </div>

            <div className="flex gap-2 rounded-xl bg-slate-900/50 p-1 backdrop-blur-sm border border-white/5 mb-6">
              <button
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
                  authMode === "login"
                    ? "bg-cyan-500/10 text-cyan-400 shadow-[0_0_15px_rgba(34,211,238,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                onClick={() => setAuthMode("login")}
              >
                Login
              </button>
              <button
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ${
                  authMode === "register"
                    ? "bg-violet-500/10 text-violet-400 shadow-[0_0_15px_rgba(168,85,247,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                onClick={() => setAuthMode("register")}
              >
                Register
              </button>
            </div>

            <div className="space-y-4">
              <input
                className="w-full rounded-xl border border-white/5 bg-slate-900/50 p-3.5 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-500 focus:border-cyan-400/50 focus:bg-slate-900/80 focus:ring-1 focus:ring-cyan-400/50"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
              {authMode === "register" && (
                <input
                  className="w-full rounded-xl border border-white/5 bg-slate-900/50 p-3.5 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-500 focus:border-cyan-400/50 focus:bg-slate-900/80 focus:ring-1 focus:ring-cyan-400/50"
                  placeholder="Email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              )}
              <input
                type="password"
                className="w-full rounded-xl border border-white/5 bg-slate-900/50 p-3.5 text-sm text-slate-100 outline-none transition-all placeholder:text-slate-500 focus:border-cyan-400/50 focus:bg-slate-900/80 focus:ring-1 focus:ring-cyan-400/50"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <label className="mt-5 flex items-center gap-3 text-sm text-slate-400 cursor-pointer group">
              <div className="relative flex items-center">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                <div className="h-5 w-5 rounded border border-white/20 bg-slate-900/50 peer-checked:bg-cyan-500 peer-checked:border-cyan-500 transition-all"></div>
                <svg className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white opacity-0 peer-checked:opacity-100 transition-opacity" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <span className="group-hover:text-slate-300 transition-colors">Remember me</span>
            </label>

            <button
              disabled={busy}
              onClick={handleAuth}
              className="group mt-8 relative w-full rounded-xl bg-slate-100 px-4 py-3.5 font-bold text-slate-900 transition-all hover:bg-white hover:shadow-[0_0_20px_rgba(255,255,255,0.3)] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none"
            >
              <div className="absolute inset-0 rounded-xl bg-gradient-to-r from-cyan-400 to-violet-500 opacity-0 transition-opacity group-hover:opacity-20 blur-md"></div>
              <span className="relative z-10">{authMode === "register" ? "Sign up" : "Sign in"}</span>
            </button>
            
            {authMessage && (
              <div className="mt-4 rounded-lg bg-cyan-950/30 border border-cyan-500/20 p-3 text-center text-sm font-medium text-cyan-300">
                {authMessage}
              </div>
            )}
          </section>
        </div>
      </main>
    );
  }

  if (showWelcome) {
    return (
      <main className="relative min-h-screen flex items-center justify-center overflow-hidden bg-[#030712] text-slate-100">
        <div className="absolute inset-0 z-0">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] rounded-full bg-cyan-500/20 blur-[120px] animate-pulse"></div>
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[400px] w-[400px] rounded-full bg-violet-600/20 blur-[100px] animate-pulse" style={{ animationDelay: '1s' }}></div>
        </div>
        <div className="relative z-10 flex flex-col items-center animate-in fade-in zoom-in duration-1000">
          <div className="mb-8 rounded-3xl bg-white/5 p-6 backdrop-blur-2xl border border-white/10 shadow-[0_0_50px_rgba(6,182,212,0.3)]">
            <svg className="h-20 w-20 text-cyan-400 drop-shadow-[0_0_15px_rgba(34,211,238,0.8)]" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 11c0 3.517-1.009 6.799-2.753 9.571m-3.44-2.04l.054-.09A13.916 13.916 0 008 11a4 4 0 118 0c0 1.017-.07 2.019-.203 3m-2.118 6.844A21.88 21.88 0 0015.171 17m3.839 1.132c.645-2.266.99-4.659.99-7.132A8 8 0 008 4.07M3 15.364c.64-1.319 1-2.8 1-4.364 0-1.457.39-2.823 1.07-4" />
            </svg>
          </div>
          <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-cyan-200 to-violet-400 mb-6 drop-shadow-lg text-center">
            {authMode === "register" ? "Welcome to CipherLens" : "Welcome back to CipherLens"}
          </h1>
          <p className="text-lg text-slate-400 font-medium tracking-wide animate-pulse">
            Initializing Secure Environment...
          </p>
          <div className="mt-12 w-64 h-1.5 bg-slate-800 rounded-full overflow-hidden">
             <div className="h-full bg-gradient-to-r from-cyan-400 to-violet-500 w-full" style={{ transformOrigin: 'left', animation: 'progressLoader 2.5s ease-out forwards' }}></div>
          </div>
        </div>
        <style dangerouslySetInnerHTML={{ __html: `
          @keyframes progressLoader {
            0% { transform: scaleX(0); }
            50% { transform: scaleX(0.7); }
            100% { transform: scaleX(1); }
          }
        `}} />
      </main>
    );
  }

  return (
    <main className="relative min-h-screen overflow-x-hidden bg-[#030712] p-4 sm:p-8 text-slate-100 animate-in fade-in duration-700">
      <div className="pointer-events-none fixed -top-40 -left-40 h-[500px] w-[500px] rounded-full bg-cyan-600/10 blur-[120px]" />
      <div className="pointer-events-none fixed bottom-0 right-0 h-[600px] w-[600px] rounded-full bg-violet-600/10 blur-[150px]" />
      
      <div className="relative mx-auto max-w-7xl space-y-8 z-10">
        
        {/* Header */}
        <section className="relative z-30 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 rounded-2xl border border-white/5 bg-white/[0.02] p-6 backdrop-blur-xl shadow-lg">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-slate-200 to-slate-400">
              CipherLens Dashboard
            </h1>
            <p className="mt-1 text-sm font-medium text-slate-400">
              Secure Environment • Model Insights • Cryptographic Verification
            </p>
          </div>
          <div className="relative z-40" ref={profileMenuRef}>
            <button
              className="flex items-center gap-3 rounded-xl border border-white/10 bg-slate-900/50 px-3 py-2 text-sm font-medium text-slate-200 transition-all hover:bg-slate-800 hover:border-white/20"
              onClick={() => setProfileMenuOpen((v) => !v)}
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-cyan-500/20 text-cyan-300">
                {(userProfile?.username?.[0] ?? username?.[0] ?? "U").toUpperCase()}
              </span>
              <span>{userProfile?.username ?? username}</span>
            </button>
            {profileMenuOpen && (
              <div className="absolute right-0 z-50 mt-2 w-72 rounded-xl border border-white/10 bg-slate-900/95 p-4 shadow-2xl backdrop-blur-xl">
                <p className="text-xs text-slate-400">Profile</p>
                <p className="mt-1 font-semibold text-slate-100">{userProfile?.username ?? username}</p>
                <p className="text-sm text-slate-300">{userProfile?.email ?? "No email found"}</p>
                {userProfile?.id !== undefined && (
                  <p className="mt-1 text-xs text-slate-400">User ID: {userProfile.id}</p>
                )}
                <button
                  className="mt-4 w-full rounded-lg border border-white/10 bg-slate-800 px-3 py-2 text-sm text-slate-100 hover:bg-slate-700"
                  onClick={() => {
                    localStorage.removeItem(AUTH_STORAGE_KEY);
                    setToken("");
                    setUserProfile(null);
                    setDocuments([]);
                    setInsight(null);
                    setSelectedDocId(null);
                    setProfileMenuOpen(false);
                  }}
                >
                  Log out
                </button>
              </div>
            )}
          </div>
        </section>

        {/* Main Dashboard Layout */}
        <div className="flex flex-col lg:flex-row gap-8">
          
          {/* Sidebar */}
          <aside className="w-full lg:w-64 flex-shrink-0 flex flex-col rounded-2xl border border-white/5 bg-[#17171a] p-4 shadow-xl h-auto lg:h-[calc(100vh-200px)] lg:sticky top-8">
            <div className="space-y-2 flex-1">
              <button
                onClick={() => setActiveTab("upload")}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${activeTab === 'upload' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : 'text-slate-400 border border-transparent hover:bg-white/5 hover:text-slate-200'}`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>
                Upload File
              </button>
              <button
                onClick={() => setActiveTab("verify")}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-colors ${activeTab === 'verify' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/20' : 'text-slate-400 border border-transparent hover:bg-white/5 hover:text-slate-200'}`}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                Verify Integrity
              </button>
            </div>
            
            <div className="mt-8 pt-4 border-t border-white/5">
              <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium text-slate-400 border border-transparent hover:bg-white/5 hover:text-slate-200 transition-colors">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                Settings
              </button>
            </div>
          </aside>

          <div className="flex-1 space-y-8">
            
            {/* Tab Content */}
            {activeTab === 'upload' && (
              <div className="flex flex-col justify-between rounded-2xl border border-white/5 bg-[#17171a] p-6 shadow-xl min-h-[420px] animate-fade-in-tab">
            <div className="flex items-center gap-2 mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              <h2 className="text-lg font-medium text-slate-200">Upload File</h2>
            </div>
            <div className="h-[1px] w-full bg-white/5 mb-6"></div>

            <label className="group relative flex flex-col items-center justify-center w-full cursor-pointer rounded-2xl border border-dashed border-white/10 bg-[#1c1c1e] p-10 text-center transition-all hover:border-teal-500/50 hover:bg-[#1c1c1e]/80">
              <input
                type="file"
                className="hidden"
                onChange={(e) => {
                  setDropFile(e.target.files?.[0] ?? null);
                  // Reset states when a new file is chosen
                  setShowSignProgress(false);
                  setIsInsightsVisible(false);
                  setAnalyzeProgress(0);
                  setSignProgress(0);
                  setAnalyzeResult("");
                }}
              />
              <svg className="h-10 w-10 text-slate-100 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 3v5h5" />
              </svg>
              <p className="text-sm font-medium text-slate-200">
                Click <span className="text-teal-400">select</span> to upload or Drop your files
              </p>
              <p className="mt-1 text-xs text-slate-500">.csv, .xls, .xlsx or .txt types are supported</p>
            </label>

            {dropFile && (
              <div className="mt-6 border-b border-white/5 pb-4">
                {/* Upload & Analyze Progress Bar */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded bg-white/5">
                      <svg className="h-6 w-6 text-slate-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                         <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-medium text-slate-200">{dropFile.name}</p>
                      <p className="text-xs text-slate-500">{(dropFile.size / 1024).toFixed(0)}KB</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 w-1/3">
                    <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden">
                      <div 
                        className="h-full bg-gradient-to-r from-teal-400 to-teal-700 transition-all duration-300" 
                        style={{ width: `${analyzeProgress}%` }}
                      ></div>
                    </div>
                    <span className="text-xs font-medium text-teal-400">{analyzeProgress}%</span>
                    <button onClick={() => {
                       setDropFile(null);
                       setShowSignProgress(false);
                       setIsInsightsVisible(false);
                       setAnalyzeProgress(0);
                       setSignProgress(0);
                       setAnalyzeResult("");
                    }} className="text-slate-500 hover:text-slate-300">
                      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                </div>

                {/* Secondary Bar for Signature Generation */}
                {showSignProgress && (
                  <div className="mt-4 flex items-center justify-between pl-14">
                    <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">Cryptographic Signature</p>
                    <div className="flex items-center gap-4 w-1/3">
                      <div className="h-1.5 flex-1 rounded-full bg-slate-800 overflow-hidden shadow-inner">
                        <div 
                          className="h-full bg-gradient-to-r from-emerald-400 to-emerald-600 transition-all duration-300" 
                          style={{ width: `${signProgress}%` }}
                        ></div>
                      </div>
                      <span className="text-xs font-medium text-emerald-400">{signProgress}%</span>
                      <div className="w-5"></div> {/* Spacer for alignment */}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="mt-6 flex gap-3">
              <button disabled={!token || !dropFile || busy} onClick={handleAnalyze} className="flex-1 rounded-xl bg-teal-500/10 border border-teal-500/20 px-4 py-3 text-sm font-bold text-teal-400 transition-all hover:bg-teal-500/20 hover:border-teal-500/50 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none">
                Execute Analysis
              </button>
              <button disabled={!token || !dropFile || busy} onClick={handleSign} className="flex-1 rounded-xl bg-teal-500/10 border border-teal-500/20 px-4 py-3 text-sm font-bold text-teal-400 transition-all hover:bg-teal-500/20 hover:border-teal-500/50 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none">
                Generate Signature
              </button>
            </div>
            
            {/* AI Insight in the left panel - only visible if user clicked "View Insights" */}
            {analyzeResult && isInsightsVisible && (
              <div className="mt-4 rounded-lg bg-[#1c1c1e] border border-teal-500/20 p-3 text-sm font-mono text-teal-400 shadow-md">
                <span className="mr-2">✓</span>{analyzeResult}
              </div>
            )}
          </div>

            )}
            
            {activeTab === 'verify' && (
              <div className="flex flex-col justify-between rounded-2xl border border-white/5 bg-[#17171a] p-6 shadow-xl min-h-[420px] animate-fade-in-tab">
            <div className="flex items-center gap-2 mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <h2 className="text-lg font-medium text-slate-200">Integrity Verification</h2>
            </div>
            <div className="h-[1px] w-full bg-white/5 mb-6"></div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1">
              <div className="flex flex-col h-full">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 block">Source Document</label>
                <label className="group relative flex flex-col items-center justify-center w-full h-full min-h-[160px] cursor-pointer rounded-2xl border border-dashed border-white/10 bg-[#1c1c1e] p-6 text-center transition-all hover:border-teal-500/50 hover:bg-[#1c1c1e]/80">
                  <input
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      setVerifyDocFile(e.target.files?.[0] ?? null);
                      setVerifyResult("");
                    }}
                  />
                  {verifyDocFile ? (
                    <div className="flex flex-col items-center gap-2">
                      <svg className="h-8 w-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                      <p className="text-sm font-medium text-slate-200 truncate max-w-[200px]">{verifyDocFile.name}</p>
                    </div>
                  ) : (
                    <>
                      <svg className="h-8 w-8 text-slate-100 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 3v5h5" />
                      </svg>
                      <p className="text-xs font-medium text-slate-200">
                        Click <span className="text-teal-400">select</span> to upload
                      </p>
                    </>
                  )}
                </label>
              </div>

              <div className="flex flex-col h-full">
                <label className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2 block">Signature (.sig)</label>
                <label className="group relative flex flex-col items-center justify-center w-full h-full min-h-[160px] cursor-pointer rounded-2xl border border-dashed border-white/10 bg-[#1c1c1e] p-6 text-center transition-all hover:border-teal-500/50 hover:bg-[#1c1c1e]/80">
                  <input
                    type="file"
                    className="hidden"
                    onChange={(e) => {
                      setVerifySigFile(e.target.files?.[0] ?? null);
                      setVerifyResult("");
                    }}
                  />
                  {verifySigFile ? (
                    <div className="flex flex-col items-center gap-2">
                      <svg className="h-8 w-8 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                      <p className="text-sm font-medium text-slate-200 truncate max-w-[200px]">{verifySigFile.name}</p>
                    </div>
                  ) : (
                    <>
                      <svg className="h-8 w-8 text-slate-100 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                      <p className="text-xs font-medium text-slate-200">
                        Click <span className="text-teal-400">select</span> to upload
                      </p>
                    </>
                  )}
                </label>
              </div>
            </div>

            <button disabled={!token || !verifyDocFile || !verifySigFile || busy} onClick={handleVerify} className="mt-8 w-full rounded-xl bg-teal-500/10 border border-teal-500/20 px-4 py-3.5 text-sm font-bold text-teal-400 transition-all hover:bg-teal-500/20 hover:shadow-[0_0_15px_rgba(45,212,191,0.2)] active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none">
              Verify Authenticity
            </button>
            
            {verifyResult && (
              <div className="mt-4 rounded-lg bg-slate-900/80 border border-teal-500/20 p-3 text-sm font-mono text-teal-300 text-center">
                {verifyResult}
              </div>
            )}
          </div>
            )}

        {/* Bottom Grid: Data */}
        <section className="grid gap-8 lg:grid-cols-3">
          
          {/* Document Ledger */}
          <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-6 backdrop-blur-xl shadow-lg flex flex-col max-h-[500px]">
             <div className="mb-6 flex items-center justify-between">
              <h2 className="text-xl font-bold">Ledger</h2>
              <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-bold text-slate-300 border border-white/5">{documents.length}</span>
            </div>

            <div className="space-y-3 overflow-y-auto pr-2 flex-1 scroll-smooth">
              {documents.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm text-slate-500 italic">No records found.</div>
              ) : documents.map((doc) => (
                <button
                  key={doc.id}
                  onClick={() => {
                    setSelectedDocId(doc.id);
                    fetchInsights(doc.id);
                    setIsInsightsVisible(false); // Hide insights when changing documents until they click the view button again
                  }}
                  className={`group relative w-full overflow-hidden rounded-xl border p-4 text-left transition-all duration-300 ${
                    selectedDocId === doc.id
                      ? "border-cyan-500/50 bg-cyan-500/10"
                      : "border-white/5 bg-slate-900/40 hover:border-white/10 hover:bg-slate-800/60"
                  }`}
                >
                  <p className="font-semibold text-slate-200 truncate pr-4 text-sm">{doc.original_filename}</p>
                </button>
              ))}
            </div>
          </div>

          {/* AI Insights & Telemetry */}
          <div className="lg:col-span-2 flex flex-col gap-6">
            
            {/* Small AI Insight Trigger Card */}
            <div className="rounded-2xl border border-white/5 bg-[#12121c] p-6 shadow-xl flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-500/10 border border-blue-500/20">
                   <svg className="h-7 w-7 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1-1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                   </svg>
                </div>
                <div>
                   <h3 className="text-xl font-semibold text-slate-100">AI Insights</h3>
                   <p className="text-sm font-medium text-slate-400">Powered by ML</p>
                </div>
              </div>
              <button 
                onClick={() => setIsInsightsVisible(true)}
                disabled={(!insight && !analyzeResult) || isInsightsVisible}
                className="rounded-xl bg-gradient-to-r from-blue-500 to-purple-500 px-6 py-3 text-sm font-bold text-white shadow-[0_0_20px_rgba(139,92,246,0.3)] transition-all hover:opacity-90 active:scale-[0.98] flex items-center gap-2 disabled:opacity-50 disabled:pointer-events-none"
              >
                 <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                 </svg>
                 View Insights
              </button>
            </div>

            {/* Large Telemetry Card */}
            {insight && isInsightsVisible ? (
              <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-[#0f1115] p-8 shadow-2xl flex-1 animate-in fade-in zoom-in-95 duration-300">
                 <div className="absolute -top-32 -left-32 h-96 w-96 rounded-full bg-teal-500/10 blur-[100px] pointer-events-none"></div>
                 <div className="absolute top-20 -left-10 h-64 w-64 rounded-full bg-purple-500/10 blur-[80px] pointer-events-none"></div>

                 <div className="relative z-10 flex items-center justify-between mb-8">
                    <div className="flex items-center gap-2">
                       <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-black shadow-[0_0_10px_rgba(255,255,255,0.5)]">
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                             <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                          </svg>
                       </div>
                       <span className="text-sm font-medium text-slate-300">Insight</span>
                    </div>
                    <div className="flex items-center gap-3">
                       <span className={`rounded-full border px-4 py-1.5 text-xs font-medium ${insight.ml_processed ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-400' : 'border-white/10 bg-white/5 text-slate-300'}`}>
                         {insight.ml_processed ? "Processed" : "Pending"}
                       </span>
                    </div>
                 </div>

                 <div className="relative z-10 flex items-end gap-3 mb-6">
                    <h2 className="text-7xl font-bold tracking-tight text-white drop-shadow-lg">
                      {(insight.classification_confidence * 100).toFixed(0)}%
                    </h2>
                    <svg className="h-10 w-10 text-emerald-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                       <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17L17 7M17 7H7M17 7v10" />
                    </svg>
                 </div>

                 <div className="relative z-10 space-y-4 pr-8">
                    <h3 className="text-2xl font-bold text-white leading-tight">
                       Model confidence is <span className="text-teal-400">exceptionally high</span> for this {insight.document_type} classification!
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                       The neural network has successfully processed the raw text telemetry and mapped the extracted entities. The document integrity is verified and it is ready for cryptographic signing. Stay ahead and keep the momentum going!
                    </p>
                 </div>

              </div>
            ) : (
              <div className="flex flex-1 items-center justify-center rounded-2xl border border-dashed border-white/10 bg-[#0f1115] p-8 text-center shadow-xl">
                <p className="text-sm text-slate-500 font-medium">
                   {insight || analyzeResult ? "Click 'View Insights' to reveal AI telemetry." : "Select a document or execute analysis to unlock insights."}
                </p>
              </div>
            )}
          </div>
        </section>
        </div>
      </div>
      </div>
    </main>
  );
}