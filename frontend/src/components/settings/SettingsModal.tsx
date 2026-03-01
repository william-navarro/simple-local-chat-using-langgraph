import { useState, useEffect, useCallback } from "react"
import { X, RotateCcw } from "lucide-react"
import { useChatStore } from "../../store/useChatStore"
import { updateSettings as updateSettingsApi } from "../../lib/api"
import type { GlobalSettings, ConversationSettings } from "../../types"
import { GeneralTab } from "./GeneralTab"
import { SystemPromptTab } from "./SystemPromptTab"
import { ToolsTab } from "./ToolsTab"
import { ApiKeysTab } from "./ApiKeysTab"
import { ProviderUrlsTab } from "./ProviderUrlsTab"

type Tab = "general" | "prompt" | "tools" | "keys" | "urls"

const TABS: { id: Tab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "prompt", label: "System Prompt" },
  { id: "tools", label: "Tools" },
  { id: "keys", label: "API Keys" },
  { id: "urls", label: "Provider URLs" },
]

const DEFAULT_SETTINGS: GlobalSettings = {
  temperature: 0.3,
  top_p: 1.0,
  max_response_tokens: 4096,
  max_history_tokens: 2000,
  system_prompt: "",
  tool_call_max_iterations: 8,
  tool_call_timeout: 120,
}

export function SettingsModal() {
  const {
    settingsModalOpen,
    setSettingsModalOpen,
    globalSettings,
    setGlobalSettings,
    activeConversationId,
    conversations,
    setConversationSettings,
    clearConversationSettings,
  } = useChatStore()

  const [tab, setTab] = useState<Tab>("general")
  const [draft, setDraft] = useState<GlobalSettings>(globalSettings)
  const [perConversation, setPerConversation] = useState(false)
  const [saving, setSaving] = useState(false)

  const activeConv = conversations.find((c) => c.id === activeConversationId)
  const hasConvOverride = !!activeConv?.settings

  // Sync draft when modal opens
  useEffect(() => {
    if (settingsModalOpen) {
      if (hasConvOverride && activeConv?.settings) {
        setDraft({ ...globalSettings, ...activeConv.settings } as GlobalSettings)
        setPerConversation(true)
      } else {
        setDraft(globalSettings)
        setPerConversation(false)
      }
    }
  }, [settingsModalOpen]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = useCallback((patch: Partial<GlobalSettings>) => {
    setDraft((prev) => ({ ...prev, ...patch }))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      if (perConversation && activeConversationId) {
        // Save only overridden fields as ConversationSettings
        const overrides: ConversationSettings = {}
        const keys: (keyof ConversationSettings)[] = [
          "temperature", "top_p", "max_response_tokens",
          "max_history_tokens", "system_prompt", "tool_call_max_iterations",
        ]
        for (const key of keys) {
          if (draft[key] !== globalSettings[key]) {
            (overrides as Record<string, unknown>)[key] = draft[key]
          }
        }
        setConversationSettings(activeConversationId, overrides)
      } else {
        // Save globally
        const updated = await updateSettingsApi(draft)
        setGlobalSettings(updated)
        // Clear per-conversation override if switching back to global
        if (activeConversationId && hasConvOverride) {
          clearConversationSettings(activeConversationId)
        }
      }
    } catch {
      // ignore errors — settings still saved locally
    } finally {
      setSaving(false)
      setSettingsModalOpen(false)
    }
  }

  const handleReset = () => {
    setDraft(DEFAULT_SETTINGS)
  }

  if (!settingsModalOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={() => setSettingsModalOpen(false)}
    >
      <div
        className="w-full max-w-lg bg-zinc-900 border border-zinc-700 rounded-xl shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-zinc-800">
          <h2 className="text-sm font-semibold text-white">Settings</h2>
          <button
            onClick={() => setSettingsModalOpen(false)}
            className="p-1 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-0 px-5 border-b border-zinc-800">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-2.5 text-xs font-medium transition-colors border-b-2 -mb-px ${
                tab === t.id
                  ? "text-violet-400 border-violet-400"
                  : "text-zinc-500 border-transparent hover:text-zinc-300"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="px-5 py-4 max-h-[60vh] overflow-y-auto">
          {tab === "general" && <GeneralTab settings={draft} onChange={handleChange} />}
          {tab === "prompt" && <SystemPromptTab settings={draft} onChange={handleChange} />}
          {tab === "tools" && <ToolsTab settings={draft} onChange={handleChange} />}
          {tab === "keys" && <ApiKeysTab />}
          {tab === "urls" && <ProviderUrlsTab />}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-3.5 border-t border-zinc-800">
          <div className="flex items-center gap-3">
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            >
              <RotateCcw size={12} />
              Reset
            </button>
            {activeConversationId && tab !== "keys" && tab !== "urls" && (
              <label className="flex items-center gap-2 text-xs text-zinc-500 cursor-pointer">
                <input
                  type="checkbox"
                  checked={perConversation}
                  onChange={(e) => setPerConversation(e.target.checked)}
                  className="accent-violet-600 rounded"
                />
                This conversation only
              </label>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSettingsModalOpen(false)}
              className="px-4 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
            >
              Cancel
            </button>
            {tab !== "keys" && tab !== "urls" && (
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-1.5 rounded-lg text-xs font-medium bg-violet-600 hover:bg-violet-500 text-white disabled:opacity-40 transition-colors"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
