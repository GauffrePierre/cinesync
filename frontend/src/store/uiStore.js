import { create } from 'zustand'
import { persist } from 'zustand/middleware'

let toastId = 0

export const useUiStore = create(
  persist(
    (set, get) => ({
      // Filtres persistés
      mediaFilter: 'all', // all | movie | tv
      platformFilter: [], // ids fournisseurs
      seenFilter: 'all', // all | unseen | seen
      upcomingView: 'grid', // grid | calendar
      swipeFilter: 'all',
      setMediaFilter: (mediaFilter) => set({ mediaFilter }),
      setSeenFilter: (seenFilter) => set({ seenFilter }),
      togglePlatform: (id) =>
        set({
          platformFilter: get().platformFilter.includes(id)
            ? get().platformFilter.filter((p) => p !== id)
            : [...get().platformFilter, id],
        }),
      clearPlatforms: () => set({ platformFilter: [] }),
      setUpcomingView: (upcomingView) => set({ upcomingView }),
      setSwipeFilter: (swipeFilter) => set({ swipeFilter }),

      // Éphémère
      searchOpen: false,
      setSearchOpen: (searchOpen) => set({ searchOpen }),
      toasts: [],
      toast: (message, kind = 'info') => {
        const id = ++toastId
        set({ toasts: [...get().toasts, { id, message, kind }] })
        setTimeout(() => set({ toasts: get().toasts.filter((t) => t.id !== id) }), 4000)
      },
      dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
    }),
    {
      name: 'cinesync-ui',
      partialize: (s) => ({
        mediaFilter: s.mediaFilter,
        platformFilter: s.platformFilter,
        seenFilter: s.seenFilter,
        upcomingView: s.upcomingView,
        swipeFilter: s.swipeFilter,
      }),
    },
  ),
)

export const toast = (message, kind) => useUiStore.getState().toast(message, kind)
