import type { GlobalSettings } from "../../types"

interface Props {
  settings: GlobalSettings
  onChange: (patch: Partial<GlobalSettings>) => void
}

export function SystemPromptTab({ settings, onChange }: Props) {
  return (
    <div className="space-y-3">
      <div>
        <label className="text-sm text-zinc-300 block mb-1.5">Custom System Prompt</label>
        <textarea
          value={settings.system_prompt}
          onChange={(e) => onChange({ system_prompt: e.target.value })}
          placeholder="You are a helpful and concise AI assistant."
          rows={8}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 placeholder-zinc-600 resize-y focus:outline-none focus:border-violet-600"
        />
        <p className="text-xs text-zinc-600 mt-1">
          Replaces the default system prompt. Leave empty to use the built-in default.
        </p>
      </div>
    </div>
  )
}
