import type { GlobalSettings } from "../../types"

interface Props {
  settings: GlobalSettings
  onChange: (patch: Partial<GlobalSettings>) => void
}

export function GeneralTab({ settings, onChange }: Props) {
  return (
    <div className="space-y-5">
      {/* Temperature */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm text-zinc-300">Temperature</label>
          <span className="text-sm text-zinc-400 tabular-nums w-12 text-right">
            {settings.temperature.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={2}
          step={0.05}
          value={settings.temperature}
          onChange={(e) => onChange({ temperature: parseFloat(e.target.value) })}
          className="w-full accent-violet-600 h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-xs text-zinc-600 mt-1">
          <span>Precise</span>
          <span>Creative</span>
        </div>
      </div>

      {/* Top P */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-sm text-zinc-300">Top P</label>
          <span className="text-sm text-zinc-400 tabular-nums w-12 text-right">
            {settings.top_p.toFixed(2)}
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={settings.top_p}
          onChange={(e) => onChange({ top_p: parseFloat(e.target.value) })}
          className="w-full accent-violet-600 h-1.5 bg-zinc-700 rounded-lg appearance-none cursor-pointer"
        />
        <div className="flex justify-between text-xs text-zinc-600 mt-1">
          <span>Focused</span>
          <span>Diverse</span>
        </div>
      </div>

      {/* Max Response Tokens */}
      <div>
        <label className="text-sm text-zinc-300 block mb-1.5">Max Response Tokens</label>
        <input
          type="number"
          min={1}
          max={128000}
          value={settings.max_response_tokens}
          onChange={(e) => onChange({ max_response_tokens: parseInt(e.target.value) || 4096 })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-violet-600"
        />
      </div>

      {/* Max History Tokens */}
      <div>
        <label className="text-sm text-zinc-300 block mb-1.5">Max History Tokens</label>
        <input
          type="number"
          min={100}
          max={100000}
          value={settings.max_history_tokens}
          onChange={(e) => onChange({ max_history_tokens: parseInt(e.target.value) || 2000 })}
          className="w-full px-3 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-sm text-zinc-200 focus:outline-none focus:border-violet-600"
        />
        <p className="text-xs text-zinc-600 mt-1">
          Messages beyond this limit are compressed into a summary.
        </p>
      </div>
    </div>
  )
}
