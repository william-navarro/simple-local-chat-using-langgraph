import { Plus, Bot, ChevronDown } from "lucide-react"
import { useState, useRef, useEffect } from "react"
import { useChatStore } from "../../store/useChatStore"
import { useHealth } from "../../hooks/useHealth"
import { ConversationItem } from "./ConversationItem"

export function Sidebar() {
  const { conversations, activeConversationId, createConversation, selectedModel, setSelectedModel } = useChatStore()
  const { online, models } = useHealth()
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  const statusLabel = online === null
    ? "checking..."
    : online
    ? "LM Studio connected"
    : "LM Studio offline"

  const statusColor = online === null
    ? "bg-zinc-500"
    : online
    ? "bg-emerald-500"
    : "bg-red-500"

  const displayModel = selectedModel
    ? selectedModel.length > 22 ? selectedModel.slice(0, 22) + "..." : selectedModel
    : "no model"

  return (
    <aside className="flex flex-col w-64 h-full bg-zinc-900 border-r border-zinc-800">
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-zinc-800">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600">
          <Bot size={16} className="text-white" />
        </div>
        <div>
          <h1 className="text-sm font-semibold text-white leading-tight">LangGraph Chat</h1>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
            <span className="text-xs text-zinc-500">{statusLabel}</span>
          </div>
        </div>
      </div>

      <div className="px-3 pt-3 pb-2 border-b border-zinc-800">
        <p className="text-xs text-zinc-500 mb-1.5 px-1">Active model</p>
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            disabled={!online || models.length === 0}
            className="flex items-center justify-between w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-xs text-zinc-300 hover:border-zinc-600 transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <span className="truncate">{displayModel}</span>
            <ChevronDown size={12} className={`shrink-0 ml-1 transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {dropdownOpen && models.length > 0 && (
            <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl max-h-48 overflow-y-auto">
              {models.map((model) => (
                <button
                  key={model}
                  onClick={() => { setSelectedModel(model); setDropdownOpen(false) }}
                  className={`w-full text-left px-3 py-2 text-xs transition-colors duration-100 ${model === selectedModel ? "bg-violet-600/30 text-violet-300" : "text-zinc-300 hover:bg-zinc-700"}`}
                >
                  {model}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="px-3 py-3">
        <button
          onClick={createConversation}
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 text-white text-sm font-medium hover:from-violet-500 hover:to-indigo-500 transition-all duration-150"
        >
          <Plus size={16} />
          New conversation
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3 space-y-0.5">
        {conversations.length === 0 ? (
          <p className="text-xs text-zinc-600 text-center mt-8 px-4">
            No conversations yet. Click New conversation to get started.
          </p>
        ) : (
          conversations.map((conv) => (
            <ConversationItem
              key={conv.id}
              conversation={conv}
              isActive={conv.id === activeConversationId}
            />
          ))
        )}
      </div>
    </aside>
  )
}
