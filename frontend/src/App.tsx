import { Sidebar } from "./components/sidebar/Sidebar"
import { ChatWindow } from "./components/chat/ChatWindow"

export default function App() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <main className="flex flex-1 min-w-0">
        <ChatWindow />
      </main>
    </div>
  )
}
