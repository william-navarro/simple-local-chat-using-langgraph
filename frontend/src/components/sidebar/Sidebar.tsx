import { Plus, Bot, ChevronDown, Settings } from "lucide-react"
import { useState, useRef, useEffect } from "react"
import { useChatStore } from "../../store/useChatStore"
import { useHealth } from "../../hooks/useHealth"
import { ConversationItem } from "./ConversationItem"
import type { LLMProvider } from "../../types"

const PROVIDER_LABELS: Record<LLMProvider, string> = {
  lm_studio: "LM Studio",
  ollama: "Ollama",
  openai: "OpenAI",
  anthropic: "Anthropic",
  google: "Google",
}

export function Sidebar() {
  const {
    conversations, activeConversationId, createConversation,
    selectedProvider, setSelectedProvider,
    selectedModel, setSelectedModel,
    setSettingsModalOpen,
  } = useChatStore()
  const { online, models, providers } = useHealth()

  const [providerOpen, setProviderOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)
  const [modelInput, setModelInput] = useState("")
  const [isTyping, setIsTyping] = useState(false)
  const providerRef = useRef<HTMLDivElement>(null)
  const modelRef = useRef<HTMLDivElement>(null)
  const modelInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (providerRef.current && !providerRef.current.contains(e.target as Node)) {
        setProviderOpen(false)
      }
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) {
        setModelOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  // Sync input text with selected model
  useEffect(() => {
    setModelInput(selectedModel)
    setIsTyping(false)
  }, [selectedModel])

  const statusLabel = online === null
    ? "checking..."
    : online
    ? `${PROVIDER_LABELS[selectedProvider]} connected`
    : `${PROVIDER_LABELS[selectedProvider]} offline`

  const statusColor = online === null
    ? "bg-zinc-500"
    : online
    ? "bg-emerald-500"
    : "bg-red-500"

  const filteredModels = isTyping && modelInput
    ? models.filter((m) => m.toLowerCase().includes(modelInput.toLowerCase()))
    : models

  const handleModelSelect = (model: string) => {
    setSelectedModel(model)
    setModelInput(model)
    setIsTyping(false)
    setModelOpen(false)
  }

  const handleModelInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && modelInput.trim()) {
      setSelectedModel(modelInput.trim())
      setModelOpen(false)
    }
    if (e.key === "Escape") {
      setModelOpen(false)
    }
  }

  return (
    <aside className="flex flex-col w-64 h-full bg-zinc-900 border-r border-zinc-800">
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-zinc-800">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600">
          <Bot size={16} className="text-white" />
        </div>
        <div className="flex-1">
          <h1 className="text-sm font-semibold text-white leading-tight">LangGraph Chat</h1>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
            <span className="text-xs text-zinc-500">{statusLabel}</span>
          </div>
        </div>
        <button
          onClick={() => setSettingsModalOpen(true)}
          className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          title="Settings"
        >
          <Settings size={16} />
        </button>
      </div>

      <div className="px-3 pt-3 pb-2 border-b border-zinc-800 space-y-2">
        {/* Provider selector */}
        <div>
          <p className="text-xs text-zinc-500 mb-1.5 px-1">Provider</p>
          <div className="relative" ref={providerRef}>
            <button
              onClick={() => setProviderOpen((v) => !v)}
              className="flex items-center justify-between w-full px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-xs text-zinc-300 hover:border-zinc-600 transition-colors duration-150"
            >
              <span className="flex items-center gap-2">
                {providers.length > 0 && (
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    providers.find((p) => p.id === selectedProvider)?.available
                      ? "bg-emerald-500"
                      : "bg-red-500"
                  }`} />
                )}
                {PROVIDER_LABELS[selectedProvider]}
              </span>
              <ChevronDown size={12} className={`shrink-0 ml-1 transition-transform ${providerOpen ? "rotate-180" : ""}`} />
            </button>

            {providerOpen && (
              <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl max-h-48 overflow-y-auto">
                {providers.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => { setSelectedProvider(p.id); setProviderOpen(false) }}
                    className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 transition-colors duration-100 ${
                      p.id === selectedProvider
                        ? "bg-violet-600/30 text-violet-300"
                        : "text-zinc-300 hover:bg-zinc-700"
                    }`}
                  >
                    <span className={`w-1.5 h-1.5 rounded-full ${p.available ? "bg-emerald-500" : "bg-red-500"}`} />
                    {p.name}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Model combobox */}
        <div>
          <p className="text-xs text-zinc-500 mb-1.5 px-1">Model</p>
          <div className="relative" ref={modelRef}>
            <div className="flex items-center w-full rounded-lg bg-zinc-800 border border-zinc-700 hover:border-zinc-600 transition-colors duration-150">
              <input
                ref={modelInputRef}
                type="text"
                value={modelInput}
                onChange={(e) => { setModelInput(e.target.value); setIsTyping(true); setModelOpen(true) }}
                onFocus={() => setModelOpen(true)}
                onKeyDown={handleModelInputKeyDown}
                placeholder="Type or select model..."
                className="flex-1 bg-transparent px-3 py-2 text-xs text-zinc-300 placeholder:text-zinc-600 outline-none min-w-0"
              />
              <button
                onClick={() => { setModelOpen((v) => !v); modelInputRef.current?.focus() }}
                className="shrink-0 px-2 py-2 text-zinc-500 hover:text-zinc-300"
              >
                <ChevronDown size={12} className={`transition-transform ${modelOpen ? "rotate-180" : ""}`} />
              </button>
            </div>

            {modelOpen && filteredModels.length > 0 && (
              <div className="absolute left-0 right-0 top-full mt-1 z-50 bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl max-h-48 overflow-y-auto">
                {filteredModels.map((model) => (
                  <button
                    key={model}
                    onClick={() => handleModelSelect(model)}
                    className={`w-full text-left px-3 py-2 text-xs transition-colors duration-100 ${
                      model === selectedModel
                        ? "bg-violet-600/30 text-violet-300"
                        : "text-zinc-300 hover:bg-zinc-700"
                    }`}
                  >
                    {model}
                  </button>
                ))}
              </div>
            )}
          </div>
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
