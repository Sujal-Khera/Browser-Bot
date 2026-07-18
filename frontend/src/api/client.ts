/**
 * Shared API Client for communicating with the BrowserBot Orchestration Server REST API.
 */

export interface Session {
  session_id: string;
  stage: string;
  created_at: string;
  updated_at: string;
  artifact_paths: Record<string, string>;
}

export interface ExtractedParameter {
  name: string;
  example_value: any;
  log_step_index: number;
  description: string;
  is_sensitive: boolean;
  is_optional: boolean;
}

export interface ExtractorOutput {
  parameters: ExtractedParameter[];
}

export interface WorkflowSpec {
  schema_version: string;
  metadata: {
    generator_version: string;
    created_at: string;
    source_session_id: string;
  };
  workflow: {
    site: string;
    start_url: string;
    description: string;
  };
  steps: any[];
  parameters: ExtractedParameter[];
  fixed_step_indices: number[];
  outputs: any[];
}

export interface ValidationReport {
  overall_success: boolean;
  file_existence: { success: boolean; message: string };
  compilation: { success: boolean; message: string };
  import_check: { success: boolean; message: string };
  runtime_dry_run: { success: boolean; message: string };
}

export interface BrowserBotPackage {
  package_version: string;
  package_name: string;
  entry_point: string;
  dependencies: string[];
  claude_config_snippet: {
    command: string;
    args: string[];
    env: Record<string, string>;
  };
  metadata: {
    browserbot_version: string;
    generated_at: string;
    source_session_id: string;
    site: string;
  };
}

const getBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    // In development mode where Vite dev server runs on a different port,
    // read the API server location or default to 127.0.0.1:8765
    if (window.location.port === "5173" || window.location.port === "5174") {
      return "http://127.0.0.1:8765";
    }
    return window.location.origin;
  }
  return "http://127.0.0.1:8765";
};

export const api = {
  async fetchSessions(): Promise<Session[]> {
    const res = await fetch(`${getBaseUrl()}/sessions`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async getSession(id: string): Promise<Session> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}`);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async startRecord(url?: string, hint?: string): Promise<Session> {
    const res = await fetch(`${getBaseUrl()}/sessions/record`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, workflow_hint: hint }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async extractParameters(id: string, dryRun: boolean = true): Promise<ExtractorOutput> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}/extract?dry_run=${dryRun}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async confirmParameters(id: string, parameters: ExtractedParameter[]): Promise<WorkflowSpec> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ parameters }),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async generateCode(id: string, dryRun: boolean = true): Promise<ValidationReport> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}/generate?dry_run=${dryRun}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async packageTool(id: string): Promise<BrowserBotPackage> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}/package`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async registerPackage(name: string): Promise<Record<string, any>> {
    const res = await fetch(`${getBaseUrl()}/packages/${name}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  async updateSessionStage(id: string, stage: string): Promise<Session> {
    const res = await fetch(`${getBaseUrl()}/sessions/${id}/stage?stage=${encodeURIComponent(stage)}`, {
      method: "POST",
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },
};
