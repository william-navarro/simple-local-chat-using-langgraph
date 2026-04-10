import { Terminal, ShieldCheck, ShieldX, ShieldOff } from "lucide-react"
import { useChatStore } from "../../store/useChatStore"

interface TerminalConfirmDialogProps {
  command: string
  shell?: string
  explanation?: string
  riskLevel?: string
  onApprove: () => void
  onApproveAlways: () => void
  onDeny: () => void
}

export function TerminalConfirmDialog({
  command,
  shell = "cmd",
  explanation,
  riskLevel,
  onApprove,
  onApproveAlways,
  onDeny,
}: TerminalConfirmDialogProps) {
  const isExecuting = useChatStore((s) => s.isExecuting)
  const isHigh = riskLevel === "high"

  return (
    <div className="mx-4 mt-2 rounded-xl border border-green-800/50 bg-green-950/60 shadow-lg shadow-green-900/20">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-green-800/30">
        <Terminal size={14} className="text-green-400" />
        <span className="text-xs font-medium text-green-300">
          Terminal Command
        </span>
        <div className="flex items-center gap-1.5 ml-auto">
          {isHigh && (
            <span className="text-xs font-medium px-1.5 py-0.5 rounded bg-red-900/60 text-red-300 border border-red-800/50">
              HIGH RISK
            </span>
          )}
          <span className="text-xs text-green-500/70 font-mono">
            {shell === "powershell" ? "PowerShell" : "CMD"}
          </span>
        </div>
      </div>

      <div className="px-3 py-2 space-y-1.5">
        {explanation && (
          <p className="text-xs text-green-400/80 italic">{explanation}</p>
        )}
        <pre className="text-sm font-mono text-green-200 bg-zinc-900/60 rounded-lg px-3 py-2 overflow-x-auto whitespace-pre-wrap break-all">
          $ {command}
        </pre>
      </div>

      <div className="flex items-center gap-2 px-3 py-2 border-t border-green-800/30">
        <button
          onClick={onApprove}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-600 hover:bg-green-500 text-white transition-colors disabled:opacity-50"
        >
          <ShieldCheck size={12} />
          Yes
        </button>
        <button
          onClick={onApproveAlways}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-800/60 hover:bg-green-700/60 text-green-200 transition-colors disabled:opacity-50"
        >
          <ShieldOff size={12} />
          Yes, don&apos;t ask again
        </button>
        <button
          onClick={onDeny}
          disabled={isExecuting}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-700 hover:bg-red-600 text-zinc-200 hover:text-white transition-colors disabled:opacity-50 ml-auto"
        >
          <ShieldX size={12} />
          No
        </button>
      </div>
    </div>
  )
}
