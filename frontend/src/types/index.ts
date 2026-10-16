// =========================================================================
// PRIMITIVE / SHARED
// =========================================================================

export type UUID = string;
export type ISODateString = string;

export type PaginationMeta = {
  total: number;
  page: number;
  limit: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
};

export type ApiResponse<T> = {
  success: boolean;
  data: T;
  message?: string;
  meta?: PaginationMeta;
};

export type ApiError = {
  success: false;
  error: string;
  message: string;
  statusCode: number;
  details?: Record<string, unknown>;
};

// =========================================================================
// USER / AUTH
// =========================================================================

export type UserRole = 'admin' | 'analyst' | 'viewer';

export type UserStatus = 'active' | 'suspended' | 'pending';

export interface User {
  id: UUID;
  email: string;
  firstName: string;
  lastName: string;
  fullName: string;
  role: UserRole;
  status: UserStatus;
  avatarUrl?: string;
  lastLoginAt?: ISODateString;
  createdAt: ISODateString;
  updatedAt: ISODateString;
  preferences?: UserPreferences;
}

export interface UserPreferences {
  theme: 'dark' | 'light' | 'system';
  notifications: {
    email: boolean;
    inApp: boolean;
    discoveryComplete: boolean;
    auditComplete: boolean;
    systemAlerts: boolean;
  };
  defaultPageSize: number;
  defaultDateRange: number; // days
}

export interface AuthTokens {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  tokenType: 'Bearer';
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// =========================================================================
// BUSINESS
// =========================================================================

export type BusinessCategory =
  | 'restaurant'
  | 'retail'
  | 'service'
  | 'healthcare'
  | 'hospitality'
  | 'automotive'
  | 'real_estate'
  | 'education'
  | 'fitness'
  | 'beauty'
  | 'legal'
  | 'financial'
  | 'technology'
  | 'construction'
  | 'other';

export type BusinessStatus = 'active' | 'inactive' | 'pending_review' | 'flagged';

export type PresenceScore = 0 | 1 | 2 | 3 | 4 | 5;

export interface BusinessLocation {
  address: string;
  city: string;
  state: string;
  zip: string;
  country: string;
  coordinates?: {
    lat: number;
    lng: number;
  };
}

export interface OnlinePresence {
  website?: string;
  hasWebsite: boolean;
  websiteScore?: number; // 0-100 quality score
  googleMyBusiness?: string;
  yelp?: string;
  facebook?: string;
  instagram?: string;
  twitter?: string;
  linkedin?: string;
  tiktok?: string;
}

export interface ReviewData {
  platform: string;
  rating: number;
  reviewCount: number;
  url?: string;
  lastUpdated: ISODateString;
}

export interface Business {
  id: UUID;
  name: string;
  category: BusinessCategory;
  subcategory?: string;
  status: BusinessStatus;
  location: BusinessLocation;
  phone?: string;
  email?: string;
  website?: string;
  onlinePresence: OnlinePresence;
  reviews: ReviewData[];
  averageRating?: number;
  totalReviews: number;
  presenceScore: PresenceScore;
  opportunityScore: number; // 0-100
  estimatedRevenueLoss?: number;
  tags: string[];
  source: string;
  sourceId?: string;
  discoveredAt: ISODateString;
  lastAuditedAt?: ISODateString;
  lastScrapedAt?: ISODateString;
  auditCount: number;
  createdAt: ISODateString;
  updatedAt: ISODateString;
}

export interface BusinessSearchParams {
  q?: string;
  category?: BusinessCategory;
  city?: string;
  state?: string;
  minScore?: number;
  maxScore?: number;
  status?: BusinessStatus;
  hasWebsite?: boolean;
  page?: number;
  limit?: number;
  sortBy?: keyof Business;
  sortOrder?: 'asc' | 'desc';
}

export interface BusinessCreatePayload {
  name: string;
  category: BusinessCategory;
  location: BusinessLocation;
  phone?: string;
  email?: string;
  website?: string;
  tags?: string[];
}

export interface BusinessUpdatePayload extends Partial<BusinessCreatePayload> {
  status?: BusinessStatus;
}

// =========================================================================
// AUDIT REPORT
// =========================================================================

export type AuditStatus = 'pending' | 'processing' | 'completed' | 'failed';

export type IssueSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export interface AuditIssue {
  id: UUID;
  category: string;
  title: string;
  description: string;
  severity: IssueSeverity;
  recommendation: string;
  estimatedImpact?: string;
  effort: 'low' | 'medium' | 'high';
  resolved: boolean;
  resolvedAt?: ISODateString;
}

export interface AuditScore {
  overall: number;
  website: number;
  seo: number;
  social: number;
  reviews: number;
  mobile: number;
  speed: number;
  accessibility: number;
}

export interface AuditReport {
  id: UUID;
  businessId: UUID;
  business?: Business;
  status: AuditStatus;
  score: AuditScore;
  issues: AuditIssue[];
  criticalIssues: number;
  highIssues: number;
  mediumIssues: number;
  lowIssues: number;
  totalIssues: number;
  recommendations: string[];
  estimatedRevenueLoss?: number;
  reportUrl?: string;
  triggeredBy: UUID;
  triggeredByUser?: User;
  startedAt?: ISODateString;
  completedAt?: ISODateString;
  processingTime?: number; // ms
  createdAt: ISODateString;
  updatedAt: ISODateString;
}

export interface AuditStats {
  totalAudits: number;
  completedAudits: number;
  failedAudits: number;
  pendingAudits: number;
  averageScore: number;
  averageIssues: number;
  criticalIssuesFound: number;
  auditsByDay: Array<{ date: string; count: number }>;
}

// =========================================================================
// DISCOVERY JOB
// =========================================================================

export type DiscoveryStatus =
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type DiscoverySource =
  | 'google_maps'
  | 'yelp'
  | 'bing_maps'
  | 'yellow_pages'
  | 'facebook'
  | 'manual';

export interface DiscoveryJobConfig {
  sources: DiscoverySource[];
  categories: BusinessCategory[];
  locations: Array<{ city: string; state: string; radius?: number }>;
  maxBusinesses?: number;
  includeChains: boolean;
  minRating?: number;
  keywords?: string[];
}

export interface DiscoveryJobProgress {
  total: number;
  discovered: number;
  processed: number;
  failed: number;
  percentage: number;
  currentSource?: DiscoverySource;
  currentLocation?: string;
  estimatedTimeRemaining?: number; // seconds
}

export interface DiscoveryJob {
  id: UUID;
  name: string;
  status: DiscoveryStatus;
  config: DiscoveryJobConfig;
  progress: DiscoveryJobProgress;
  businessesFound: number;
  newBusinesses: number;
  updatedBusinesses: number;
  duplicatesSkipped: number;
  errors: string[];
  createdBy: UUID;
  createdByUser?: User;
  startedAt?: ISODateString;
  pausedAt?: ISODateString;
  completedAt?: ISODateString;
  estimatedCompletedAt?: ISODateString;
  createdAt: ISODateString;
  updatedAt: ISODateString;
}

export interface DiscoveryJobCreatePayload {
  name: string;
  config: DiscoveryJobConfig;
  scheduleAt?: ISODateString;
}

// =========================================================================
// ANALYTICS
// =========================================================================

export interface DashboardStats {
  totalBusinesses: number;
  businessesDelta: number; // percentage change vs last period
  averagePresenceScore: number;
  presenceScoreDelta: number;
  pendingAudits: number;
  auditsDelta: number;
  activeDiscoveries: number;
  discoveriesDelta: number;
  estimatedTotalOpportunity: number;
  opportunityDelta: number;
}

export interface IndustryBreakdown {
  category: BusinessCategory;
  label: string;
  count: number;
  percentage: number;
  averageScore: number;
  totalOpportunity: number;
  color: string;
}

export interface GeographyData {
  state: string;
  city?: string;
  count: number;
  averageScore: number;
  topCategory: BusinessCategory;
  coordinates?: { lat: number; lng: number };
}

export interface TrendDataPoint {
  date: string;
  businesses: number;
  audits: number;
  discoveredBusinesses: number;
  averageScore: number;
}

export interface OpportunityData {
  score: number; // 0-100 opportunity score
  count: number;
  label: string;
  estimatedValue: number;
}

export interface AnalyticsDashboard {
  stats: DashboardStats;
  trends: TrendDataPoint[];
  industries: IndustryBreakdown[];
  geography: GeographyData[];
  opportunities: OpportunityData[];
  topOpportunities: Business[];
  recentAudits: AuditReport[];
  activeJobs: DiscoveryJob[];
}

export interface AnalyticsFilters {
  dateRange?: { from: ISODateString; to: ISODateString };
  categories?: BusinessCategory[];
  states?: string[];
  cities?: string[];
  minScore?: number;
  maxScore?: number;
}

// =========================================================================
// EXPORT
// =========================================================================

export type ExportFormat = 'csv' | 'excel' | 'pdf';
export type ExportStatus = 'queued' | 'processing' | 'completed' | 'failed';

export interface ExportJob {
  id: UUID;
  format: ExportFormat;
  status: ExportStatus;
  filters?: BusinessSearchParams;
  totalRecords?: number;
  processedRecords?: number;
  fileUrl?: string;
  fileSize?: number;
  error?: string;
  createdAt: ISODateString;
  completedAt?: ISODateString;
  expiresAt?: ISODateString;
}

export interface ExportCreatePayload {
  format: ExportFormat;
  filters?: BusinessSearchParams;
  columns?: string[];
  includeAuditData?: boolean;
}

// =========================================================================
// WEBSOCKET / REAL-TIME
// =========================================================================

export type WSMessageType =
  | 'DISCOVERY_PROGRESS'
  | 'DISCOVERY_COMPLETE'
  | 'DISCOVERY_FAILED'
  | 'AUDIT_STARTED'
  | 'AUDIT_PROGRESS'
  | 'AUDIT_COMPLETE'
  | 'AUDIT_FAILED'
  | 'EXPORT_COMPLETE'
  | 'SYSTEM_STATS'
  | 'LIVE_METRICS'
  | 'NOTIFICATION'
  | 'ERROR'
  | 'PING'
  | 'PONG';

export interface WSMessage<T = unknown> {
  type: WSMessageType;
  payload: T;
  timestamp: ISODateString;
  jobId?: UUID;
}

export interface WSDiscoveryProgress {
  jobId: UUID;
  jobName: string;
  status: DiscoveryStatus;
  progress: DiscoveryJobProgress;
}

export interface WSAuditProgress {
  auditId: UUID;
  businessId: UUID;
  businessName: string;
  status: AuditStatus;
  progress: number; // 0-100
  currentStep?: string;
}

export interface WSSystemStats {
  cpuUsage: number;
  memoryUsage: number;
  activeWorkers: number;
  queuedJobs: number;
  dbConnections: number;
  requestsPerMinute: number;
  timestamp: ISODateString;
}

export interface WSLiveMetrics {
  businessesDiscoveredToday: number;
  auditsCompletedToday: number;
  activeUsers: number;
  systemLoad: number;
  timestamp: ISODateString;
}

export interface WSNotification {
  id: UUID;
  title: string;
  message: string;
  type: 'info' | 'success' | 'warning' | 'error';
  actionUrl?: string;
  read: boolean;
}

// =========================================================================
// UI STATE
// =========================================================================

export interface Notification extends WSNotification {
  receivedAt: ISODateString;
}

export interface PageMeta {
  title: string;
  breadcrumbs?: Array<{ label: string; href?: string }>;
}
