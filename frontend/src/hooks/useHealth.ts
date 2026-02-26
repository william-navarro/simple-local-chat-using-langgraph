import { useEffect, useState } from "react"
import { fetchLMStudioStatus, fetchLMStudioModels } from "../lib/api"
import { useChatStore } from "../store/useChatStore"

export function useHealth() {
  const [online, setOnline] = useState<boolean | null>(null)
  const [models, setModels] = useState<string[]>([])
  const { selectedModel, setSelectedModel } = useChatStore()

  useEffect(() => {
    let cancelled = false

    const check = async () => {
      const isOnline = await fetchLMStudioStatus()
      if (cancelled) return
      setOnline(isOnline)

      if (isOnline) {
        const available = await fetchLMStudioModels()
        if (cancelled) return
        setModels(available)
        if (available.length > 0 && !selectedModel) {
          setSelectedModel(available[0])
        }
      } else {
        setModels([])
      }
    }

    check()
    const interval = setInterval(check, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [selectedModel, setSelectedModel])

  return { online, models }
}
