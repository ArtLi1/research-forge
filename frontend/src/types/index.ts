export interface ServiceHealth {
  status: 'healthy' | 'unhealthy'
  detail?: string
}

export interface HealthResponse {
  status: 'healthy' | 'degraded'
  services: Record<string, ServiceHealth>
}

export interface SystemSettings {
  app_name: string
  llm_base_url?: string
  llm_model?: string
  llm_api_key_configured: boolean
  embedding_provider: string
  embedding_model: string
  chroma_endpoint: string
  chroma_data_dir: string
  third_party_notice: string
}

export interface Project {
  id: string
  name: string
  description: string
  research_goal?: string
  preferences: Record<string, unknown>
  exclusions: string[]
  created_at: string
  updated_at: string
}

export interface Paper {
  id: string
  title: string
  authors: string[]
  year?: number
  venue?: string
  doi?: string
  arxiv_id?: string
  keywords: string[]
  source_type: string
  parse_status: string
  parse_error?: string
  global_metadata: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface BackgroundTask {
  id: string
  task_type: string
  status: string
  stage: string
  progress: number
  message: string
  resource_type?: string
  resource_id?: string
  payload: Record<string, unknown>
  error?: string
  created_at: string
  updated_at: string
}

export interface UploadResult {
  paper: Paper
  task_id?: string
  duplicate: boolean
}

export interface EvidenceItem {
  paper_id: string
  paper_title: string
  year?: number
  content: string
  knowledge_type?: string
  name?: string
  section?: string
  page_start?: number
  page_end?: number
  source_type: string
  score: number
}

export interface EvidencePack {
  query: string
  items: EvidenceItem[]
  missing_information: string[]
  conflicting_groups: string[][]
}

export interface EvidenceRef {
  chunk_id: string
  page?: number
  section?: string
  quote: string
  confidence: number
}

export interface ScenarioKnowledge {
  name: string
  description: string
  key_challenge: string
  innovation_point?: string
}

export interface AlgorithmKnowledge {
  name: string
  core_idea: string
  key_mechanism: string
  innovation_point: string
}

export interface KnowledgeCard {
  card_id: string
  paper_id: string
  version_id: string
  version_number: number
  status: string
  validation_status: string
  extraction_model: string
  prompt_version: string
  content: {
    scenarios: ScenarioKnowledge[]
    algorithms: AlgorithmKnowledge[]
  }
  created_at: string
}

export interface Evidence {
  id: string
  paper_id: string
  chunk_id: string
  target_type: string
  target_id: string
  field_path: string
  page?: number
  section?: string
  quote: string
  source_type: string
  confidence: number
  created_at: string
}

export interface MetadataDefinition {
  id: string
  name: string
  description: string
  scope: 'global_paper' | 'project_paper'
  value_type: 'text' | 'boolean' | 'single_enum' | 'multi_enum' | 'rating'
  options?: string[]
  auto_extract: boolean
  created_at: string
}

export interface ProjectKnowledgeItem {
  statement: string
  source_type: 'paper' | 'user_idea' | 'accepted_scheme'
  source_id: string
  evidence_ids: string[]
}

export interface ProjectKnowledge {
  id: string
  project_id: string
  category: string
  version_id: string
  version_number: number
  content: { items: ProjectKnowledgeItem[] }
  change_summary: string
  source_paper_ids: string[]
  source_idea_ids: string[]
  created_at: string
}

export interface UserIdea {
  id: string
  project_id: string
  title: string
  content: string
  idea_type: string
  status: string
  tags: string[]
  linked_paper_ids: string[]
  linked_evidence_ids: string[]
  agent_evaluation?: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ComparisonDimension {
  dimension: string
  entries: Array<{ paper_id: string; statement: string }>
  conclusion_type: 'explicit_difference' | 'synthesis' | 'unconfirmed'
  conclusion: string
}

export interface ComparisonResult {
  paper_ids: string[]
  dimensions: ComparisonDimension[]
  summary: string
}

export interface CandidateSchemeContent {
  name: string
  core_research_question: string[]
  scenario_innovation: string[]
  model_level_changes: string[]
  algorithm_innovation: string[]
  possible_paper_contributions: string[]
  borrowed_mechanisms: string[]
  expected_advantages: string[]
  combination_rationale: string[]
  required_assumptions: string[]
  simple_combination_risk: string
  novelty_risk: string
  compatibility_risks: string[]
  implementation_complexity: 'low' | 'medium' | 'high'
  recommendation_score: number
  unresolved_questions: string[]
}

export interface SchemeRiskAssessment {
  diversity_passed: boolean
  goal_alignment_passed: boolean
  compatibility_passed: boolean
  hard_constraint_violations: string[]
  compatibility_risks: string[]
  remaining_risks: string[]
}

export interface CandidateVersion {
  id: string
  candidate_id: string
  version_number: number
  parent_version_id?: string
  content: CandidateSchemeContent
  user_instruction?: string
  risk_assessment: SchemeRiskAssessment
  model: string
  prompt_version: string
  created_at: string
}

export interface CandidateScheme {
  id: string
  project_id: string
  title: string
  status: 'candidate' | 'accepted' | 'abandoned'
  current_version_id: string
  langgraph_thread_id: string
  abandoned_reason?: string
  accepted_at?: string
  current_version: CandidateVersion
  versions?: CandidateVersion[]
  created_at: string
  updated_at: string
}

export interface AgentTraceStep {
  name: string
  status: string
  query_count?: number
  result_count?: number
  candidate_count?: number
  issue_count?: number
  retry?: boolean
}

export interface AgentTrace {
  run_id: string
  status: string
  goal: string
  retrieval_plan: Record<string, string[]>
  retrieved_scenario_count: number
  retrieved_algorithm_count: number
  retrieved_knowledge_ids: string[]
  candidate_count: number
  retry_count: number
  validation: Record<string, boolean>
  steps: AgentTraceStep[]
}
