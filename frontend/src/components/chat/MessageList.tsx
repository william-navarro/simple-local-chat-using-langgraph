import { useEffect, useRef } from "react"
import { MessageItem } from "./MessageItem"
import { useChatStore } from "../../store/useChatStore"
import type { Message } from "../../types"

interface MessageListProps {
  messages: Message[]
}

export function MessageList({ messages }: MessageListProps) {
  const { isStreaming, isThinking } = useChatStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isStreaming, isThinking])

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-zinc-800 border border-zinc-700 mx-auto mb-4">
            <span className="text-3xl">💬</span>
          </div>
          <p className="text-zinc-400 text-sm font-medium">Como posso ajudar?</p>
          <p className="text-zinc-600 text-xs mt-1">Digite uma mensagem para comecar</p>
        </div>
      </div>
    )
  }

  const lastAssistantIndex = messages.reduce(
    (acc, m, i) => (m.role === "assistant" ? i : acc),
    -1
  )

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-4 space-y-4 scrollbar-thin scrollbar-thumb-zinc-700 scrollbar-track-transparent min-w-0">
      {messages.map((message, index) => (
        <MessageItem
          key={message.id}
          message={message}
          isStreaming={isStreaming && index === lastAssistantIndex && message.role === "assistant"}
          isThinking={isThinking && index === lastAssistantIndex && message.role === "assistant"}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  )
}
