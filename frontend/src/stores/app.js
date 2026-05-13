import { defineStore } from 'pinia'
import { setBaseURL, getBaseURL } from '@/api/request'
import { getSyncStatus } from '@/api/health'

export const useAppStore = defineStore('app', {
  state: () => ({
    baseURL: getBaseURL(),
    serverOnline: false,
  }),
  actions: {
    setServerURL(url) {
      this.baseURL = url
      setBaseURL(url)
    },
    async checkServer() {
      try {
        await getSyncStatus()
        this.serverOnline = true
      } catch {
        this.serverOnline = false
      }
    },
  },
})
