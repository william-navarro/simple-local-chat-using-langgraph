import { useState, useEffect } from "react"
import { Eye, EyeOff, LogIn, CheckCircle, XCircle, Circle } from "lucide-react"
import type { ApiKeysState } from "../../types"
import {
  fetchApiKeys,
  updateApiKeys,
  fetchProviderStatus,
  triggerCliProxyLogin,
  fetchCliProxyAuthStatus,
} from "../../lib/api"

const KEY_FIELDS: { key: keyof ApiKeysState; label: string; provider: string }[] = [
  { key: "openai_api_key", label: "OpenAI", provider: "openai" },
  { key: "anthropic_api_key", label: "Anthropic", provider: "anthropic" },
  { key: "google_api_key", label: "Google", provider: "google" },
]

type KeyStatus = "checking" | "valid" | "invalid" | "empty"

export function ApiKeysTab() {
  const [masked, setMasked] = useState<ApiKeysState>({
    openai_api_key: "",
    anthropic_api_key: "",
    google_api_key: "",
  })
  const [edits, setEdits] = useState<Partial<ApiKeysState>>({})
  const [visible, setVisible] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState("")
  const [keyStatus, setKeyStatus] = useState<Record<string, KeyStatus>>({})

  // CLI Proxy state
  const [loginStatus, setLoginStatus] = useState<{ message: string; ok: boolean } | null>(null)
  const [loggingIn, setLoggingIn] = useState(false)
  const [proxyAuth, setProxyAuth] = useState<{ authenticated: boolean; running: boolean } | null>(null)
  const [checkingProxy, setCheckingProxy] = useState(true)

  useEffect(() => {
    fetchApiKeys()
      .then((keys) => {
        setMasked(keys)
        // Check status for each key that has a value
        for (const { key, provider } of KEY_FIELDS) {
          if (keys[key] && keys[key] !== "") {
            setKeyStatus((prev) => ({ ...prev, [key]: "checking" }))
            fetchProviderStatus(provider).then((online) => {
              setKeyStatus((prev) => ({ ...prev, [key]: online ? "valid" : "invalid" }))
            })
          } else {
            setKeyStatus((prev) => ({ ...prev, [key]: "empty" }))
          }
        }
      })
      .catch(() => {})

    // Check CLI Proxy auth
    fetchCliProxyAuthStatus()
      .then(setProxyAuth)
      .catch(() => setProxyAuth({ authenticated: false, running: false }))
      .finally(() => setCheckingProxy(false))
  }, [])

  const handleSave = async () => {
    const toSave = Object.fromEntries(
      Object.entries(edits).filter(([, v]) => v !== undefined && v !== "")
    )
    if (Object.keys(toSave).length === 0) return

    setSaving(true)
    setStatus("")
    try {
      await updateApiKeys(toSave)
      setStatus("Saved!")
      setEdits({})
      const updated = await fetchApiKeys()
      setMasked(updated)
      // Re-check status for saved keys
      for (const { key, provider } of KEY_FIELDS) {
        if (toSave[key as keyof ApiKeysState]) {
          setKeyStatus((prev) => ({ ...prev, [key]: "checking" }))
          fetchProviderStatus(provider).then((online) => {
            setKeyStatus((prev) => ({ ...prev, [key]: online ? "valid" : "invalid" }))
          })
        }
      }
    } catch {
      setStatus("Failed to save")
    } finally {
      setSaving(false)
    }
  }

  const handleLogin = async () => {
    setLoggingIn(true)
    setLoginStatus(null)
    try {
      const result = await triggerCliProxyLogin()
      setLoginStatus({ message: result.message, ok: result.status === "ok" })
      if (result.status === "ok") {
        // Refresh auth status
        const authResult = await fetchCliProxyAuthStatus()
        setProxyAuth(authResult)
      }
    } catch {
      setLoginStatus({ message: "Failed to connect to backend", ok: false })
    } finally {
      setLoggingIn(false)
    }
  }

  const StatusIcon = ({ status }: { status: KeyStatus }) => {
    switch (status) {
      case "checking":
        return <Circle size={12} className="text-zinc-500 animate-pulse" />
      case "valid":
        return <CheckCircle size={12} className="text-emerald-400" />
      case "invalid":
        return <XCircle size={12} className="text-red-400" />
      default:
        return null
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-zinc-500">
        API keys are stored on the server (.env file). Only masked values are shown here.
      </p>

      {KEY_FIELDS.map(({ key, label }) => {
        const isEditing = edits[key] !== undefined
        const displayValue = isEditing ? edits[key]! : masked[key]

        return (
          <div key={key}>
            <label className="text-sm text-zinc-300 mb-1.5 flex items-center gap-2">
              {label}
              <StatusIcon status={keyStatus[key] ?? "empty"} />
              {keyStatus[key] === "valid" && (
                <span className="text-[10px] text-emerald-400">Active</span>
              )}
              {keyStatus[key] === "invalid" && (
                <span className="text-[10px] text-red-400">Invalid key</span>
              )}
            </label>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={visible[key] ? "text" : "password"}
                  value={displayValue}
                  placeholder={masked[key] || "Not configured"}
                  onChange={(e) => setEdits({ ...edits, [key]: e.target.value })}
                  className="w-full px-3 py-2 pr-9 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-violet-600"
                />
                <button
                  type="button"
                  onClick={() => setVisible({ ...visible, [key]: !visible[key] })}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300"
                >
                  {visible[key] ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>
          </div>
        )
      })}

      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving || Object.keys(edits).length === 0}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? "Saving..." : "Save Keys"}
        </button>
        {status && (
          <span className={`text-xs ${status === "Saved!" ? "text-emerald-400" : "text-red-400"}`}>
            {status}
          </span>
        )}
      </div>

      {/* CLI Proxy OAuth Login */}
      <div className="mt-6 pt-4 border-t border-zinc-800">
        <h3 className="text-sm font-medium text-zinc-300 mb-1 flex items-center gap-2">
          CLI Proxy (Google OAuth)
          {!checkingProxy && proxyAuth && (
            proxyAuth.authenticated ? (
              <>
                <CheckCircle size={12} className="text-emerald-400" />
                <span className="text-[10px] text-emerald-400 font-normal">Authenticated</span>
              </>
            ) : proxyAuth.running ? (
              <>
                <XCircle size={12} className="text-amber-400" />
                <span className="text-[10px] text-amber-400 font-normal">Token expired</span>
              </>
            ) : (
              <>
                <XCircle size={12} className="text-zinc-500" />
                <span className="text-[10px] text-zinc-500 font-normal">Not running</span>
              </>
            )
          )}
        </h3>
        <p className="text-xs text-zinc-500 mb-3">
          Authenticate with Google to use Gemini models via CLI Proxy. A browser window will open on the server.
        </p>
        <div className="flex items-center gap-3">
          {(!proxyAuth?.authenticated || loginStatus?.ok === false) && (
            <button
              onClick={handleLogin}
              disabled={loggingIn}
              className="flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <LogIn size={14} />
              {loggingIn ? "Logging in..." : "Login with Google"}
            </button>
          )}
          {proxyAuth?.authenticated && !loginStatus && (
            <button
              onClick={handleLogin}
              disabled={loggingIn}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <LogIn size={12} />
              Re-authenticate
            </button>
          )}
          {loginStatus && (
            <span className={`text-xs ${loginStatus.ok ? "text-emerald-400" : "text-red-400"}`}>
              {loginStatus.message}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
