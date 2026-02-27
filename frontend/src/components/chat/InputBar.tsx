import { useState, useRef, useCallback } from "react"
import { Send, Square, Paperclip, Brain, Globe, Terminal, Archive, X } from "lucide-react"
import { useChatStore } from "../../store/useChatStore"
import { useStream } from "../../hooks/useStream"
import { TerminalConfirmDialog } from "./TerminalConfirmDialog"

export function InputBar() {
  const [input, setInput] = useState("")
  const [imageBase64, setImageBase64] = useState<string | undefined>()
  const [imageMediaType, setImageMediaType] = useState<string | undefined>()
  const [imagePreview, setImagePreview] = useState<string | undefined>()

  const { isStreaming, isThinking, isSearching, isExecuting, isCompressing, thinkingMode, webSearchMode, terminalMode, pendingTerminalCommand, toggleThinkingMode, toggleWebSearchMode, toggleTerminalMode } = useChatStore()
  const { sendMessage, stopStreaming, resolveTerminalApproval } = useStream()
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleSubmit = useCallback(async () => {
    const trimmed = input.trim()
    if ((!trimmed && !imageBase64) || isStreaming) return

    const b64 = imageBase64
    const mime = imageMediaType
    setInput("")
    setImageBase64(undefined)
    setImageMediaType(undefined)
    setImagePreview(undefined)
    if (textareaRef.current) textareaRef.current.style.height = "auto"

    await sendMessage(trimmed || " ", b64, mime)
  }, [input, imageBase64, imageMediaType, isStreaming, sendMessage])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = "auto"
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const result = reader.result as string
      setImageBase64(result.split(",")[1])
      setImageMediaType(file.type)
      setImagePreview(result)
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const canSend = (input.trim().length > 0 || !!imageBase64) && !isStreaming

  return (
    <div className="border-t border-zinc-800 bg-zinc-950">
      {pendingTerminalCommand && (
        <TerminalConfirmDialog
          command={pendingTerminalCommand.command}
          onApprove={() => resolveTerminalApproval("approve")}
          onApproveAlways={() => resolveTerminalApproval("approve_always")}
          onDeny={() => resolveTerminalApproval("deny")}
        />
      )}

      <div className="px-4 py-3">
      {imagePreview && (
        <div className="relative inline-block mb-2">
          <img
            src={imagePreview}
            alt="preview"
            className="h-20 w-20 object-cover rounded-lg border border-zinc-700"
          />
          <button
            onClick={() => { setImageBase64(undefined); setImageMediaType(undefined); setImagePreview(undefined) }}
            className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-zinc-700 hover:bg-red-600 flex items-center justify-center transition-colors"
          >
            <X size={10} className="text-white" />
          </button>
        </div>
      )}

      <div className="flex items-end gap-2 bg-zinc-900 border border-zinc-700 rounded-xl px-3 py-2 focus-within:border-violet-500 transition-colors duration-150">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          title="Attach image"
          className="shrink-0 p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed mb-0.5"
        >
          <Paperclip size={16} />
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileChange}
        />

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
          rows={1}
          disabled={isStreaming}
          className="flex-1 bg-transparent text-sm text-zinc-100 placeholder-zinc-500 resize-none outline-none min-h-[36px] max-h-[160px] leading-relaxed py-1.5 disabled:opacity-50"
        />

        <button
          onClick={toggleWebSearchMode}
          disabled={isStreaming}
          title={webSearchMode ? "Disable web search (model decides when to search)" : "Enable web search (model decides when to search)"}
          className={`
            shrink-0 p-1.5 rounded-lg transition-colors duration-150 mb-0.5
            disabled:opacity-40 disabled:cursor-not-allowed
            ${webSearchMode
              ? "text-blue-400 bg-blue-900/40 hover:bg-blue-900/60"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }
          `}
        >
          <Globe size={16} />
        </button>

        <button
          onClick={toggleTerminalMode}
          disabled={isStreaming}
          title={terminalMode ? "Disable terminal (model decides when to execute)" : "Enable terminal (model decides when to execute)"}
          className={`
            shrink-0 p-1.5 rounded-lg transition-colors duration-150 mb-0.5
            disabled:opacity-40 disabled:cursor-not-allowed
            ${terminalMode
              ? "text-green-400 bg-green-900/40 hover:bg-green-900/60"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }
          `}
        >
          <Terminal size={16} />
        </button>

        <button
          onClick={toggleThinkingMode}
          disabled={isStreaming}
          title={thinkingMode ? "Disable thinking mode" : "Enable thinking mode"}
          className={`
            shrink-0 p-1.5 rounded-lg transition-colors duration-150 mb-0.5
            disabled:opacity-40 disabled:cursor-not-allowed
            ${thinkingMode
              ? "text-violet-400 bg-violet-900/40 hover:bg-violet-900/60"
              : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
            }
          `}
        >
          <Brain size={16} />
        </button>

        {isStreaming ? (
          <button
            onClick={stopStreaming}
            title="Stop generation"
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg mb-0.5 bg-gradient-to-br from-red-600 to-red-700 text-white transition-all duration-150 hover:from-red-500 hover:to-red-600"
          >
            <Square size={12} fill="currentColor" />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!canSend}
            className="shrink-0 flex items-center justify-center w-8 h-8 rounded-lg mb-0.5 bg-gradient-to-br from-violet-600 to-indigo-600 text-white transition-all duration-150 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={14} />
          </button>
        )}
      </div>

      <div className="flex items-center justify-between mt-1.5 px-1">
        <span className="text-xs text-zinc-600">
          {pendingTerminalCommand
            ? <span className="text-yellow-400 animate-pulse flex items-center gap-1"><Terminal size={11} /> Waiting for approval...</span>
            : isCompressing
            ? <span className="text-cyan-400 animate-pulse flex items-center gap-1"><Archive size={11} /> Compressing...</span>
            : isExecuting
            ? <span className="text-green-400 animate-pulse flex items-center gap-1"><Terminal size={11} /> Running command...</span>
            : isSearching
            ? <span className="text-blue-400 animate-pulse flex items-center gap-1"><Globe size={11} /> Searching...</span>
            : isThinking
            ? <span className="text-violet-400 animate-pulse flex items-center gap-1"><Brain size={11} /> Thinking...</span>
            : thinkingMode && webSearchMode && terminalMode ? "Thinking + Web + Terminal (auto)"
            : thinkingMode && webSearchMode ? "Thinking + Web Search (auto)"
            : thinkingMode && terminalMode ? "Thinking + Terminal (auto)"
            : webSearchMode && terminalMode ? "Web + Terminal (auto)"
            : thinkingMode ? "Thinking enabled"
            : webSearchMode ? "Web Search (auto)"
            : terminalMode ? "Terminal (auto)"
            : "LangGraph + LM Studio"
          }
        </span>
        <div className="flex items-center gap-2">
          {webSearchMode && (
            <span className="text-xs text-blue-500 font-medium">Web auto</span>
          )}
          {terminalMode && (
            <span className="text-xs text-green-500 font-medium">Terminal auto</span>
          )}
          {thinkingMode && (
            <span className="text-xs text-violet-500 font-medium">Thinking ON</span>
          )}
        </div>
      </div>
      </div>
    </div>
  )
}
