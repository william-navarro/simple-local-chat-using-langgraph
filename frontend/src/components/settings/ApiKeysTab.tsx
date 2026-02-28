import { useState, useEffect } from "react"
import { Eye, EyeOff } from "lucide-react"
import type { ApiKeysState } from "../../types"
import { fetchApiKeys, updateApiKeys } from "../../lib/api"

const KEY_FIELDS: { key: keyof ApiKeysState; label: string }[] = [
  { key: "openai_api_key", label: "OpenAI" },
  { key: "anthropic_api_key", label: "Anthropic" },
  { key: "google_api_key", label: "Google" },
]

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

  useEffect(() => {
    fetchApiKeys()
      .then(setMasked)
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
      await updateApiKeys(toSave)
      setStatus("Saved!")
      setEdits({})
      // Refresh masked values
      const updated = await fetchApiKeys()
      setMasked(updated)
    } catch {
      setStatus("Failed to save")
    } finally {
      setSaving(false)
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
            <label className="text-sm text-zinc-300 block mb-1.5">{label}</label>
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
    </div>
  )
}
