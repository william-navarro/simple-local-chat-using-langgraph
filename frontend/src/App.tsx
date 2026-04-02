import { useEffect } from "react"
import { Sidebar } from "./components/sidebar/Sidebar"
import { ChatWindow } from "./components/chat/ChatWindow"
import { SettingsModal } from "./components/settings/SettingsModal"
import { useSettingsSync } from "./hooks/useSettings"
import { useChatStore } from "./store/useChatStore"

export default function App() {
  useSettingsSync()
  const loadConversations = useChatStore((s) => s.loadConversations)

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <main className="flex flex-1 min-w-0">
        <ChatWindow />
      </main>
      <SettingsModal />
    </div>
  )
}
