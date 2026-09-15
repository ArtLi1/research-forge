import { api } from './client'
import type {
  AgentTrace,
  BackgroundTask,
  CandidateScheme,
  ComparisonResult,
  Evidence,
  EvidencePack,
  HealthResponse,
  KnowledgeCard,
  MetadataDefinition,
  Paper,
  Project,
  ProjectKnowledge,
  SystemSettings,
  UploadResult,
  UserIdea,
} from '@/types'

export const getHealth = () => api.get<HealthResponse>('/health').then((r) => r.data)
export const getSystemSettings = () =>
  api.get<SystemSettings>('/settings').then((r) => r.data)
export const retryTask = (taskId: string) =>
  api.post<BackgroundTask>(`/tasks/${taskId}/retry`).then((r) => r.data)
export const getProjects = () => api.get<Project[]>('/projects').then((r) => r.data)
export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data)
export const createProject = (payload: Partial<Project>) =>
  api.post<Project>('/projects', payload).then((r) => r.data)
export const deleteProject = (id: string) => api.delete(`/projects/${id}`)
export const getPapers = (knowledgeReady = false) =>
  api
    .get<Paper[]>('/papers', { params: knowledgeReady ? { knowledge_ready: true } : undefined })
    .then((r) => r.data)
export const getProjectPapers = (id: string) =>
  api.get<Paper[]>(`/projects/${id}/papers`).then((r) => r.data)
export const removeProjectPaper = (projectId: string, paperId: string) =>
  api.delete(`/projects/${projectId}/papers/${paperId}`)
export const getPaper = (id: string) => api.get<Paper>(`/papers/${id}`).then((r) => r.data)
export const getKnowledge = (id: string) =>
  api.get<KnowledgeCard>(`/papers/${id}/knowledge`).then((r) => r.data)
export const getEvidence = (id: string) =>
  api.get<Evidence[]>(`/papers/${id}/evidence`).then((r) => r.data)
export const extractKnowledge = (id: string) =>
  api.post(`/papers/${id}/extract`).then((r) => r.data)
export const getMetadataDefinitions = () =>
  api.get<MetadataDefinition[]>('/metadata-definitions').then((r) => r.data)
export const createMetadataDefinition = (payload: Partial<MetadataDefinition>) =>
  api.post<MetadataDefinition>('/metadata-definitions', payload).then((r) => r.data)
export const setPaperMetadataValue = (paperId: string, definitionId: string, value: unknown) =>
  api.put(`/papers/${paperId}/metadata/${definitionId}`, { value }).then((r) => r.data)
export const autoFillMetadata = (paperId: string, definitionId: string) =>
  api.post(`/papers/${paperId}/metadata/${definitionId}/auto-fill`).then((r) => r.data)
export const comparePapers = (paperIds: string[]) =>
  api
    .post<ComparisonResult>('/papers/compare', { paper_ids: paperIds }, { timeout: 180_000 })
    .then((r) => r.data)
export const getProjectKnowledge = (projectId: string) =>
  api
    .get<ProjectKnowledge[]>(`/projects/${projectId}/knowledge`)
    .then((r) => r.data)
export const getIdeas = (projectId: string) =>
  api.get<UserIdea[]>(`/projects/${projectId}/ideas`).then((r) => r.data)
export const createIdea = (projectId: string, payload: Partial<UserIdea>) =>
  api.post<UserIdea>(`/projects/${projectId}/ideas`, payload).then((r) => r.data)
export const updateIdea = (ideaId: string, payload: Partial<UserIdea>) =>
  api.patch<UserIdea>(`/ideas/${ideaId}`, payload).then((r) => r.data)
export const deleteIdea = (ideaId: string) => api.delete(`/ideas/${ideaId}`)
export const evaluateIdea = (ideaId: string) =>
  api.post<UserIdea>(`/ideas/${ideaId}/evaluate`).then((r) => r.data)
export const getSchemes = (projectId: string) =>
  api.get<CandidateScheme[]>(`/projects/${projectId}/schemes`).then((r) => r.data)
export const getScheme = (schemeId: string) =>
  api.get<CandidateScheme>(`/schemes/${schemeId}`).then((r) => r.data)
export const getSchemeAgentTrace = (schemeId: string) =>
  api.get<AgentTrace>(`/schemes/${schemeId}/agent-run`).then((r) => r.data)
export const generateSchemes = (
  projectId: string,
  payload: { goal: string; selected_idea_ids: string[]; candidate_count: 3 },
) =>
  api
    .post<BackgroundTask>(`/projects/${projectId}/schemes/generate`, payload)
    .then((r) => r.data)
export const reviseScheme = (schemeId: string, instruction: string, versionId: string) =>
  api
    .post<CandidateScheme>(
      `/schemes/${schemeId}/revise`,
      { instruction, expected_version_id: versionId },
      { timeout: 300_000 },
    )
    .then((r) => r.data)
export const acceptScheme = (schemeId: string, versionId: string) =>
  api
    .post<CandidateScheme>(`/schemes/${schemeId}/accept`, {
      expected_version_id: versionId,
    })
    .then((r) => r.data)
export const abandonScheme = (schemeId: string, reason: string) =>
  api
    .post<CandidateScheme>(`/schemes/${schemeId}/abandon`, { reason })
    .then((r) => r.data)

export async function uploadPapers(files: File[], projectId?: string): Promise<UploadResult[]> {
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  if (projectId) form.append('project_id', projectId)
  return api.post<UploadResult[]>('/papers/upload', form).then((r) => r.data)
}

export const searchPapers = (payload: {
  query: string
  scope: 'global' | 'project'
  project_id?: string
  top_k: number
}) => api.post<EvidencePack>('/search', payload).then((r) => r.data)
