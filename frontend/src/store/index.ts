import { create } from 'zustand';
import { persist, createJSONStorage, devtools } from 'zustand/middleware';
import type {
  User,
  DiscoveryJob,
  Notification,
  WSSystemStats,
  WSLiveMetrics,
  WSDiscoveryProgress,
} from '@/types';

// =========================================================================
// AUTH STORE
// =========================================================================

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthActions {
  setAuth: (user: User, accessToken: string, refreshToken: string) => void;
  setUser: (user: User) => void;
  setTokens: (accessToken: string, refreshToken: string) => void;
  setLoading: (loading: boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState & AuthActions>()(
  devtools(
    persist(
      (set) => ({
        // State
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        isLoading: false,

        // Actions
        setAuth: (user, accessToken, refreshToken) =>
          set(
            {
              user,
              accessToken,
              refreshToken,
              isAuthenticated: true,
              isLoading: false,
            },
            false,
            'auth/setAuth'
          ),

        setUser: (user) =>
          set({ user }, false, 'auth/setUser'),

        setTokens: (accessToken, refreshToken) =>
          set({ accessToken, refreshToken }, false, 'auth/setTokens'),

        setLoading: (isLoading) =>
          set({ isLoading }, false, 'auth/setLoading'),

        logout: () =>
          set(
            {
              user: null,
              accessToken: null,
              refreshToken: null,
              isAuthenticated: false,
              isLoading: false,
            },
            false,
            'auth/logout'
          ),
      }),
      {
        name: 'bi-auth-store',
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
          user: state.user,
          accessToken: state.accessToken,
          refreshToken: state.refreshToken,
          isAuthenticated: state.isAuthenticated,
        }),
      }
    ),
    { name: 'AuthStore' }
  )
);

// =========================================================================
// UI STORE
// =========================================================================

type ActivePage =
  | 'dashboard'
  | 'businesses'
  | 'discovery'
  | 'audits'
  | 'analytics'
  | 'export'
  | 'settings'
  | 'users';

interface UIState {
  sidebarOpen: boolean;
  sidebarCollapsed: boolean;
  activePage: ActivePage;
  notifications: Notification[];
  unreadNotifications: number;
  commandPaletteOpen: boolean;
  searchQuery: string;
  isSearching: boolean;
  modalStack: string[];
  theme: 'dark' | 'light';
}

interface UIActions {
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setActivePage: (page: ActivePage) => void;
  addNotification: (notification: Notification) => void;
  markNotificationRead: (id: string) => void;
  markAllNotificationsRead: () => void;
  clearNotifications: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setSearchQuery: (query: string) => void;
  setIsSearching: (searching: boolean) => void;
  pushModal: (modalId: string) => void;
  popModal: () => void;
  closeModal: (modalId: string) => void;
  setTheme: (theme: 'dark' | 'light') => void;
}

export const useUIStore = create<UIState & UIActions>()(
  devtools(
    persist(
      (set, get) => ({
        // State
        sidebarOpen: true,
        sidebarCollapsed: false,
        activePage: 'dashboard',
        notifications: [],
        unreadNotifications: 0,
        commandPaletteOpen: false,
        searchQuery: '',
        isSearching: false,
        modalStack: [],
        theme: 'dark',

        // Actions
        setSidebarOpen: (sidebarOpen) =>
          set({ sidebarOpen }, false, 'ui/setSidebarOpen'),

        toggleSidebar: () =>
          set(
            (state) => ({ sidebarOpen: !state.sidebarOpen }),
            false,
            'ui/toggleSidebar'
          ),

        setSidebarCollapsed: (sidebarCollapsed) =>
          set({ sidebarCollapsed }, false, 'ui/setSidebarCollapsed'),

        toggleSidebarCollapsed: () =>
          set(
            (state) => ({ sidebarCollapsed: !state.sidebarCollapsed }),
            false,
            'ui/toggleSidebarCollapsed'
          ),

        setActivePage: (activePage) =>
          set({ activePage }, false, 'ui/setActivePage'),

        addNotification: (notification) =>
          set(
            (state) => ({
              notifications: [notification, ...state.notifications].slice(0, 50),
              unreadNotifications: state.unreadNotifications + 1,
            }),
            false,
            'ui/addNotification'
          ),

        markNotificationRead: (id) =>
          set(
            (state) => {
              const notifications = state.notifications.map((n) =>
                n.id === id ? { ...n, read: true } : n
              );
              const unreadNotifications = notifications.filter((n) => !n.read).length;
              return { notifications, unreadNotifications };
            },
            false,
            'ui/markNotificationRead'
          ),

        markAllNotificationsRead: () =>
          set(
            (state) => ({
              notifications: state.notifications.map((n) => ({ ...n, read: true })),
              unreadNotifications: 0,
            }),
            false,
            'ui/markAllNotificationsRead'
          ),

        clearNotifications: () =>
          set(
            { notifications: [], unreadNotifications: 0 },
            false,
            'ui/clearNotifications'
          ),

        setCommandPaletteOpen: (commandPaletteOpen) =>
          set({ commandPaletteOpen }, false, 'ui/setCommandPaletteOpen'),

        setSearchQuery: (searchQuery) =>
          set({ searchQuery }, false, 'ui/setSearchQuery'),

        setIsSearching: (isSearching) =>
          set({ isSearching }, false, 'ui/setIsSearching'),

        pushModal: (modalId) =>
          set(
            (state) => ({
              modalStack: [...state.modalStack, modalId],
            }),
            false,
            'ui/pushModal'
          ),

        popModal: () =>
          set(
            (state) => ({
              modalStack: state.modalStack.slice(0, -1),
            }),
            false,
            'ui/popModal'
          ),

        closeModal: (modalId) => {
          const { modalStack } = get();
          set(
            { modalStack: modalStack.filter((id) => id !== modalId) },
            false,
            'ui/closeModal'
          );
        },

        setTheme: (theme) =>
          set({ theme }, false, 'ui/setTheme'),
      }),
      {
        name: 'bi-ui-store',
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
          sidebarCollapsed: state.sidebarCollapsed,
          theme: state.theme,
        }),
      }
    ),
    { name: 'UIStore' }
  )
);

// =========================================================================
// DISCOVERY STORE
// =========================================================================

interface JobProgressEntry {
  jobId: string;
  jobName: string;
  percentage: number;
  discovered: number;
  total: number;
  currentSource?: string;
  currentLocation?: string;
  estimatedTimeRemaining?: number;
  status: string;
  lastUpdated: string;
}

interface DiscoveryState {
  activeJobs: DiscoveryJob[];
  jobProgress: Record<string, JobProgressEntry>;
  completedJobIds: string[];
  totalActiveCount: number;
}

interface DiscoveryActions {
  setActiveJobs: (jobs: DiscoveryJob[]) => void;
  addActiveJob: (job: DiscoveryJob) => void;
  removeActiveJob: (jobId: string) => void;
  updateJobStatus: (jobId: string, status: DiscoveryJob['status']) => void;
  updateJobProgress: (progress: WSDiscoveryProgress) => void;
  markJobCompleted: (jobId: string) => void;
  clearCompletedJobs: () => void;
}

export const useDiscoveryStore = create<DiscoveryState & DiscoveryActions>()(
  devtools(
    (set) => ({
      // State
      activeJobs: [],
      jobProgress: {},
      completedJobIds: [],
      totalActiveCount: 0,

      // Actions
      setActiveJobs: (activeJobs) =>
        set(
          { activeJobs, totalActiveCount: activeJobs.length },
          false,
          'discovery/setActiveJobs'
        ),

      addActiveJob: (job) =>
        set(
          (state) => {
            const exists = state.activeJobs.find((j) => j.id === job.id);
            if (exists) return state;
            const activeJobs = [job, ...state.activeJobs];
            return { activeJobs, totalActiveCount: activeJobs.length };
          },
          false,
          'discovery/addActiveJob'
        ),

      removeActiveJob: (jobId) =>
        set(
          (state) => {
            const activeJobs = state.activeJobs.filter((j) => j.id !== jobId);
            const jobProgress = { ...state.jobProgress };
            delete jobProgress[jobId];
            return { activeJobs, jobProgress, totalActiveCount: activeJobs.length };
          },
          false,
          'discovery/removeActiveJob'
        ),

      updateJobStatus: (jobId, status) =>
        set(
          (state) => ({
            activeJobs: state.activeJobs.map((job) =>
              job.id === jobId ? { ...job, status } : job
            ),
          }),
          false,
          'discovery/updateJobStatus'
        ),

      updateJobProgress: (progressData) =>
        set(
          (state) => ({
            jobProgress: {
              ...state.jobProgress,
              [progressData.jobId]: {
                jobId: progressData.jobId,
                jobName: progressData.jobName,
                percentage: progressData.progress.percentage,
                discovered: progressData.progress.discovered,
                total: progressData.progress.total,
                currentSource: progressData.progress.currentSource,
                currentLocation: progressData.progress.currentLocation,
                estimatedTimeRemaining: progressData.progress.estimatedTimeRemaining,
                status: progressData.status,
                lastUpdated: new Date().toISOString(),
              },
            },
          }),
          false,
          'discovery/updateJobProgress'
        ),

      markJobCompleted: (jobId) =>
        set(
          (state) => ({
            completedJobIds: [...state.completedJobIds, jobId].slice(-20),
            activeJobs: state.activeJobs.filter((j) => j.id !== jobId),
            totalActiveCount: Math.max(0, state.totalActiveCount - 1),
          }),
          false,
          'discovery/markJobCompleted'
        ),

      clearCompletedJobs: () =>
        set({ completedJobIds: [] }, false, 'discovery/clearCompletedJobs'),
    }),
    { name: 'DiscoveryStore' }
  )
);

// =========================================================================
// SYSTEM STORE
// =========================================================================

interface SystemState {
  systemStats: WSSystemStats | null;
  liveMetrics: WSLiveMetrics | null;
  isHealthy: boolean;
  lastHeartbeat: string | null;
  wsConnected: boolean;
  version: string | null;
  environment: 'development' | 'staging' | 'production' | null;
}

interface SystemActions {
  setSystemStats: (stats: WSSystemStats) => void;
  setLiveMetrics: (metrics: WSLiveMetrics) => void;
  setHealth: (healthy: boolean) => void;
  setHeartbeat: (timestamp: string) => void;
  setWsConnected: (connected: boolean) => void;
  setSystemInfo: (info: { version: string; environment: SystemState['environment'] }) => void;
  resetSystemState: () => void;
}

const INITIAL_SYSTEM_STATE: SystemState = {
  systemStats: null,
  liveMetrics: null,
  isHealthy: true,
  lastHeartbeat: null,
  wsConnected: false,
  version: null,
  environment: null,
};

export const useSystemStore = create<SystemState & SystemActions>()(
  devtools(
    (set) => ({
      ...INITIAL_SYSTEM_STATE,

      setSystemStats: (systemStats) =>
        set({ systemStats }, false, 'system/setSystemStats'),

      setLiveMetrics: (liveMetrics) =>
        set({ liveMetrics }, false, 'system/setLiveMetrics'),

      setHealth: (isHealthy) =>
        set({ isHealthy }, false, 'system/setHealth'),

      setHeartbeat: (lastHeartbeat) =>
        set({ lastHeartbeat }, false, 'system/setHeartbeat'),

      setWsConnected: (wsConnected) =>
        set({ wsConnected }, false, 'system/setWsConnected'),

      setSystemInfo: ({ version, environment }) =>
        set({ version, environment }, false, 'system/setSystemInfo'),

      resetSystemState: () =>
        set(INITIAL_SYSTEM_STATE, false, 'system/reset'),
    }),
    { name: 'SystemStore' }
  )
);
