import { useState } from "react"
import { Trash2, MessageSquare } from "lucide-react"
import { DeleteDialog } from "./DeleteDialog"
import { useChatStore } from "../../store/useChatStore"
import type { Conversation } from "../../types"

interface ConversationItemProps {
  conversation: Conversation
  isActive: boolean
}

export function ConversationItem({ conversation, isActive }: ConversationItemProps) {
  const { setActiveConversation, deleteConversation } = useChatStore()
  const [showDelete, setShowDelete] = useState(false)

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    setShowDelete(true)
  }

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
    if (diffDays === 0) return "Today"
    if (diffDays === 1) return "Yesterday"
    if (diffDays < 7) return `${diffDays} days ago`
    return date.toLocaleDateString("en-US", { day: "2-digit", month: "short" })
  }

  return (
    <>
      <div
        onClick={() => setActiveConversation(conversation.id)}
        className={`
          group flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer
          transition-colors duration-150 select-none
          ${isActive ? "bg-zinc-700 text-white" : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200"}
        `}
      >
        <MessageSquare size={15} className="shrink-0 opacity-60" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate leading-tight">{conversation.title}</p>
          <p className="text-xs text-zinc-500 mt-0.5">{formatDate(conversation.updatedAt)}</p>
        </div>
        <button
          onClick={handleDelete}
          className="shrink-0 p-1 rounded transition-colors duration-150 text-zinc-600 hover:text-red-400 hover:bg-zinc-700 opacity-0 group-hover:opacity-100"
          aria-label="Delete conversation"
        >
          <Trash2 size={14} />
        </button>
      </div>

      <DeleteDialog
        open={showDelete}
        onConfirm={() => { deleteConversation(conversation.id); setShowDelete(false) }}
        onCancel={() => setShowDelete(false)}
      />
    </>
  )
}
