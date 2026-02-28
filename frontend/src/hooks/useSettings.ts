import { useEffect } from "react"
import { useChatStore } from "../store/useChatStore"
import { fetchSettings } from "../lib/api"

export function useSettingsSync() {
  const setGlobalSettings = useChatStore((s) => s.setGlobalSettings)

  useEffect(() => {
    fetchSettings()
      .then(setGlobalSettings)
      .catch(() => {
        // Backend unreachable — keep local defaults
      })
  }, [setGlobalSettings])
}
