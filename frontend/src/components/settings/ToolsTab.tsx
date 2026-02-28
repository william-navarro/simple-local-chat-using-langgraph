import type { GlobalSettings } from "../../types"

interface Props {
  settings: GlobalSettings
  onChange: (patch: Partial<GlobalSettings>) => void
}

export function ToolsTab({ settings, onChange }: Props) {
  return (
    <div className="space-y-5">
      {/* Max iterations */}
      <div>
        <label className="text-sm text-zinc-300 block mb-1.5">Max Tool Call Iterations</label>
        <input
          type="number"
          min={1}
          max={20}
          value={settings.tool_call_max_iterations}
          onChange={(e) => onChange({ tool_call_max_iterations: parseInt(e.target.value) || 8 })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-violet-600"
        />
        <p className="text-xs text-zinc-600 mt-1">
          Max number of tool call rounds per request (ReAct loop limit).
        </p>
      </div>

      {/* Timeout */}
      <div>
        <label className="text-sm text-zinc-300 block mb-1.5">Tool Call Timeout (seconds)</label>
        <input
          type="number"
          min={5}
          max={300}
          value={settings.tool_call_timeout}
          onChange={(e) => onChange({ tool_call_timeout: parseInt(e.target.value) || 120 })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-violet-600"
        />
        <p className="text-xs text-zinc-600 mt-1">
          Timeout for each individual LLM call during tool use.
        </p>
      </div>
    </div>
  )
}
