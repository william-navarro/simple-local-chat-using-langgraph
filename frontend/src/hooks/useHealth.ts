import { useEffect, useState } from "react"
import { fetchProviders, fetchProviderModels } from "../lib/api"
import { useChatStore } from "../store/useChatStore"
import type { ProviderInfo } from "../types"

export function useHealth() {
  const [providers, setProviders] = useState<ProviderInfo[]>([])
  const [models, setModels] = useState<string[]>([])
  const { selectedProvider, selectedModel, setSelectedModel } = useChatStore()

  // Poll all providers for availability
  useEffect(() => {
    let cancelled = false

    const check = async () => {
      const list = await fetchProviders()
      if (!cancelled) setProviders(list)
    }

    check()
    const interval = setInterval(check, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  // Fetch models when selectedProvider changes
  useEffect(() => {
    let cancelled = false

    const fetchModels = async () => {
      const available = await fetchProviderModels(selectedProvider)
      if (cancelled) return
      setModels(available)
      if (available.length > 0 && !selectedModel) {
        setSelectedModel(available[0])
      }
    }

    fetchModels()
    const interval = setInterval(fetchModels, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [selectedProvider, selectedModel, setSelectedModel])

  const online = providers.find((p) => p.id === selectedProvider)?.available ?? null

  return { online, models, providers }
}
