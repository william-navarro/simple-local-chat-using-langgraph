import { useChatStore } from "../../store/useChatStore"
import { MessageList } from "./MessageList"
import { InputBar } from "./InputBar"
import { Bot, Brain, Globe, Terminal, Archive } from "lucide-react"

export function ChatWindow() {
  const { activeConversationId, getActiveConversation, createConversation, isThinking, isSearching, isExecuting, isCompressing, pendingTerminalCommand } = useChatStore()
  const conversation = getActiveConversation()

  if (!activeConversationId || !conversation) {
    return (
      <div className="flex-1 flex items-center justify-center bg-zinc-950">
        <div className="text-center">
          <div className="flex items-center justify-center w-20 h-20 rounded-2xl bg-gradient-to-br from-violet-600/20 to-indigo-600/20 border border-violet-500/20 mx-auto mb-5">
            <Bot size={36} className="text-violet-400" />
          </div>
          <h2 className="text-white font-semibold text-lg mb-2">
            Welcome to LangGraph Chat
          </h2>
          <p className="text-zinc-500 text-sm mb-6 max-w-xs">
            Select a conversation from the sidebar or create a new one to get started.
          </p>
          <button
            onClick={createConversation}
            className="px-5 py-2.5 rounded-lg text-sm font-medium bg-gradient-to-r from-violet-600 to-indigo-600 text-white hover:from-violet-500 hover:to-indigo-500 transition-all duration-150"
          >
            New conversation
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col flex-1 h-full bg-zinc-950">
      <div className="flex items-center px-4 py-3 border-b border-zinc-800 bg-zinc-900 overflow-hidden">
        <h2 className="text-sm font-medium text-zinc-200 truncate min-w-0 flex-1">
          {conversation.title}
        </h2>
        <div className="ml-auto flex items-center gap-3">
          {isCompressing && (
            <span className="flex items-center gap-1.5 text-xs text-cyan-400 animate-pulse">
              <Archive size={12} />
              Compressing...
            </span>
          )}
          {pendingTerminalCommand && (
            <span className="flex items-center gap-1.5 text-xs text-yellow-400 animate-pulse">
              <Terminal size={12} />
              Waiting for approval...
            </span>
          )}
          {isExecuting && !pendingTerminalCommand && (
            <span className="flex items-center gap-1.5 text-xs text-green-400 animate-pulse">
              <Terminal size={12} />
              Running command...
            </span>
          )}
          {isSearching && !isExecuting && (
            <span className="flex items-center gap-1.5 text-xs text-blue-400 animate-pulse">
              <Globe size={12} />
              Searching the web...
            </span>
          )}
          {isThinking && !isSearching && !isExecuting && (
            <span className="flex items-center gap-1.5 text-xs text-violet-400 animate-pulse">
              <Brain size={12} />
              Thinking...
            </span>
          )}
          <span className="text-xs text-zinc-600">
            {conversation.messages.length} message{conversation.messages.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      <MessageList messages={conversation.messages} />
      <InputBar />
    </div>
  )
}
