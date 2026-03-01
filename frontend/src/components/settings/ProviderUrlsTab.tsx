import { useState, useEffect } from "react"
import type { ProviderUrlsState } from "../../types"
import { fetchProviderUrls, updateProviderUrls } from "../../lib/api"

const URL_FIELDS: { key: keyof ProviderUrlsState; label: string; placeholder: string }[] = [
  { key: "lm_studio_url", label: "LM Studio", placeholder: "http://localhost:1234/v1" },
  { key: "ollama_url", label: "Ollama", placeholder: "http://localhost:11434/v1" },
  { key: "cli_proxy_url", label: "CLI Proxy", placeholder: "http://localhost:8090/v1" },
]

export function ProviderUrlsTab() {
  const [current, setCurrent] = useState<ProviderUrlsState>({
    lm_studio_url: "",
    ollama_url: "",
    cli_proxy_url: "",
  })
  const [edits, setEdits] = useState<Partial<ProviderUrlsState>>({})
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState("")

  useEffect(() => {
    fetchProviderUrls()
      .then(setCurrent)
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    const toSave = Object.fromEntries(
      Object.entries(edits).filter(([, v]) => v !== undefined && v !== "")
    )
    if (Object.keys(toSave).length === 0) return

    setSaving(true)
    setStatus("")
    try {
      await updateProviderUrls(toSave)
      setStatus("Saved!")
      setEdits({})
      const updated = await fetchProviderUrls()
      setCurrent(updated)
    } catch {
      setStatus("Failed to save")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-zinc-500">
        Base URLs for local/self-hosted providers. Changes are saved to the server .env file.
      </p>

      {URL_FIELDS.map(({ key, label, placeholder }) => {
        const isEditing = edits[key] !== undefined
        const displayValue = isEditing ? edits[key]! : current[key]

        return (
          <div key={key}>
            <label className="text-sm text-zinc-300 block mb-1.5">{label}</label>
            <input
              type="text"
              value={displayValue}
              placeholder={placeholder}
              onChange={(e) => setEdits({ ...edits, [key]: e.target.value })}
              className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-violet-600"
            />
          </div>
        )
      })}

      <div className="flex items-center gap-3 pt-2">
        <button
          onClick={handleSave}
          disabled={saving || Object.keys(edits).length === 0}
          className="px-4 py-1.5 rounded-lg text-sm font-medium bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? "Saving..." : "Save URLs"}
        </button>
        {status && (
          <span className={`text-xs ${status === "Saved!" ? "text-emerald-400" : "text-red-400"}`}>
            {status}
          </span>
        )}
      </div>
    </div>
  )
}
