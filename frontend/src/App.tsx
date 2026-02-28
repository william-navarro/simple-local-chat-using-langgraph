import { Sidebar } from "./components/sidebar/Sidebar"
import { ChatWindow } from "./components/chat/ChatWindow"
import { SettingsModal } from "./components/settings/SettingsModal"
import { useSettingsSync } from "./hooks/useSettings"

export default function App() {
  useSettingsSync()

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
