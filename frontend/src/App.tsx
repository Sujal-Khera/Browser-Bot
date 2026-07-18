import { useState, useEffect } from "react";
import {
  Play,
  Check,
  X,
  Plus,
  AlertCircle,
  RefreshCw,
  Layers,
  Terminal,
  Settings,
  CheckCircle2,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";
import { api } from "./api/client";
import type { Session, ExtractedParameter, ValidationReport, BrowserBotPackage } from "./api/client";
import "./App.css";

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSession, setSelectedSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form states for Recording
  const [recordUrl, setRecordUrl] = useState("");
  const [recordHint, setRecordHint] = useState("");

  // Extracted parameter states
  const [parameters, setParameters] = useState<(ExtractedParameter & { enabled: boolean })[]>([]);
  const [newParam, setNewParam] = useState<Partial<ExtractedParameter>>({
    name: "",
    example_value: "",
    description: "",
    is_sensitive: false,
    is_optional: false,
  });
  const [showAddParam, setShowAddParam] = useState(false);
  const [paramErrors, setParamErrors] = useState<Record<string, string>>({});

  // Generate / Package / Register states
  const [validationReport, setValidationReport] = useState<ValidationReport | null>(null);
  const [packageMetadata, setPackageMetadata] = useState<BrowserBotPackage | null>(null);
  const [registrationConfig, setRegistrationConfig] = useState<Record<string, any> | null>(null);

  // Poll for recording progress
  useEffect(() => {
    let interval: any;
    if (selectedSession && selectedSession.stage === "recording") {
      interval = setInterval(async () => {
        try {
          const sess = await api.getSession(selectedSession.session_id);
          setSelectedSession(sess);
          if (sess.stage !== "recording") {
            clearInterval(interval);
            loadSessionData(sess);
          }
        } catch (err) {
          console.error("Failed to poll session status:", err);
        }
      }, 1500);
    }
    return () => clearInterval(interval);
  }, [selectedSession]);

  // Load all sessions on startup
  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const data = await api.fetchSessions();
      setSessions(data);
    } catch (err: any) {
      setError(err.message || "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  };

  // Determine stage & fetch metadata
  const loadSessionData = async (session: Session) => {
    setSelectedSession(session);
    setError(null);
    setLoading(true);
    try {
      if (session.stage === "recorded") {
        // Automatically extract parameters on entering confirmation
        const data = await api.extractParameters(session.session_id);
        setParameters(
          data.parameters.map((p) => ({
            ...p,
            enabled: true,
          }))
        );
      } else if (session.stage === "extracted" || session.stage === "confirmed" || session.stage === "generated" || session.stage === "packaged") {
        // If already extracted, fetch the confirmed/extractor JSON from the backend manually or re-trigger extract safely
        const data = await api.extractParameters(session.session_id);
        setParameters(
          data.parameters.map((p) => ({
            ...p,
            enabled: true,
          }))
        );
      }
    } catch (err: any) {
      setError(err.message || "Failed to extract session details");
    } finally {
      setLoading(false);
    }
  };

  const handleStartRecording = async (e: React.FormEvent) => {
    e.preventDefault();
    if (recordUrl && !recordUrl.startsWith("http://") && !recordUrl.startsWith("https://")) {
      setError("URL must start with http:// or https://");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const session = await api.startRecord(recordUrl || undefined, recordHint || undefined);
      setSelectedSession(session);
      setRecordUrl("");
      setRecordHint("");
    } catch (err: any) {
      setError(err.message || "Failed to start recording session");
    } finally {
      setLoading(false);
    }
  };

  const validateParamName = (name: string, index: number): string | null => {
    if (!name) return "Name is required";
    if (!/^[a-z_][a-z0-9_]*$/.test(name)) return "Must be snake_case (lowercase, alphanumeric, underscores)";
    
    // Check uniqueness
    const dup = parameters.find((p, idx) => p.name === name && idx !== index && p.enabled);
    if (dup) return "Parameter name must be unique";
    return null;
  };

  const handleParamChange = (index: number, key: keyof ExtractedParameter | "enabled", value: any) => {
    const updated = [...parameters];
    updated[index] = { ...updated[index], [key]: value } as any;
    setParameters(updated);

    // Revalidate
    if (key === "name" || key === "enabled") {
      const err = validateParamName(updated[index].name, index);
      setParamErrors((prev) => ({
        ...prev,
        [index]: err || "",
      }));
    }
  };

  const handleAddManualParam = () => {
    const name = newParam.name?.trim();
    if (!name) return;

    const err = validateParamName(name, -1);
    if (err) {
      setError(`Manual Parameter Error: ${err}`);
      return;
    }

    const param: ExtractedParameter & { enabled: boolean } = {
      name,
      example_value: newParam.example_value || "dummy_value",
      description: newParam.description || "Manually added parameter",
      log_step_index: 0,
      is_sensitive: !!newParam.is_sensitive,
      is_optional: !!newParam.is_optional,
      enabled: true,
    };

    setParameters([...parameters, param]);
    setNewParam({ name: "", example_value: "", description: "", is_sensitive: false, is_optional: false });
    setShowAddParam(false);
    setError(null);
  };

  const handleConfirmParameters = async () => {
    if (!selectedSession) return;
    setError(null);

    // Validate all enabled parameter names
    const errors: Record<string, string> = {};
    let hasErrors = false;
    parameters.forEach((p, idx) => {
      if (p.enabled) {
        const err = validateParamName(p.name, idx);
        if (err) {
          errors[idx] = err;
          hasErrors = true;
        }
      }
    });

    if (hasErrors) {
      setParamErrors(errors);
      setError("Please resolve validation errors in parameter names.");
      return;
    }

    setLoading(true);
    try {
      const enabledParams = parameters.filter((p) => p.enabled).map(({ enabled, ...rest }) => rest);
      await api.confirmParameters(selectedSession.session_id, enabledParams);
      const updatedSess = await api.getSession(selectedSession.session_id);
      setSelectedSession(updatedSess);
    } catch (err: any) {
      setError(err.message || "Failed to confirm parameters");
    } finally {
      setLoading(false);
    }
  };

  const handleGenerateCode = async () => {
    if (!selectedSession) return;
    setLoading(true);
    setError(null);
    try {
      const report = await api.generateCode(selectedSession.session_id);
      setValidationReport(report);
      const updatedSess = await api.getSession(selectedSession.session_id);
      setSelectedSession(updatedSess);
    } catch (err: any) {
      setError(err.message || "Code generation failed");
    } finally {
      setLoading(false);
    }
  };

  const handlePackageTool = async () => {
    if (!selectedSession) return;
    setLoading(true);
    setError(null);
    try {
      const pkg = await api.packageTool(selectedSession.session_id);
      setPackageMetadata(pkg);
      const updatedSess = await api.getSession(selectedSession.session_id);
      setSelectedSession(updatedSess);
    } catch (err: any) {
      setError(err.message || "Packaging failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterPackage = async () => {
    if (!packageMetadata) return;
    setLoading(true);
    setError(null);
    try {
      const config = await api.registerPackage(packageMetadata.package_name);
      setRegistrationConfig(config);
      if (selectedSession) {
        // Force complete step updates
        const updatedSess = await api.updateSessionStage(selectedSession.session_id, "registered");
        setSelectedSession(updatedSess);
      }
    } catch (err: any) {
      setError(err.message || "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const getWizardStep = (stage: string): number => {
    switch (stage) {
      case "recording":
        return 1;
      case "recorded":
      case "extracted":
        return 2;
      case "confirmed":
        return 3;
      case "generated":
      case "packaged":
      case "registered":
        return 4;
      default:
        return 1;
    }
  };

  const resetWizard = () => {
    setSelectedSession(null);
    setValidationReport(null);
    setPackageMetadata(null);
    setRegistrationConfig(null);
    setParameters([]);
    setError(null);
    fetchSessions();
  };

  const currentStep = selectedSession ? getWizardStep(selectedSession.stage) : 0;

  return (
    <div className="flex flex-col min-h-screen bg-[var(--bg)] text-[var(--text)] font-sans antialiased">
      {/* Header */}
      <header className="border-b border-[var(--border)] px-8 py-5 flex items-center justify-between bg-[var(--bg)]">
        <div className="flex items-center space-x-3 cursor-pointer" onClick={resetWizard}>
          <div className="w-10 h-10 rounded-xl bg-purple-600 flex items-center justify-center text-white shadow-md shadow-purple-500/20">
            <Layers className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-semibold m-0 tracking-tight text-[var(--text-h)]">BrowserBot</h1>
            <p className="text-xs text-gray-500">v2.2 Orchestrator Wizard</p>
          </div>
        </div>

        {selectedSession && (
          <button
            onClick={resetWizard}
            className="px-4 py-2 text-sm rounded-lg border border-[var(--border)] hover:bg-gray-50 dark:hover:bg-gray-800 transition"
          >
            Exit Wizard
          </button>
        )}
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-5xl w-full mx-auto p-8 flex flex-col justify-start">
        {/* Error Alert */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 rounded-xl flex items-start space-x-3 text-red-700 dark:text-red-400">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div className="text-sm font-medium">{error}</div>
          </div>
        )}

        {!selectedSession ? (
          /* Dashboard / Session Selector */
          <div className="space-y-8 animate-fade-in">
            <div className="text-left space-y-2">
              <h2 className="text-3xl font-bold tracking-tight text-[var(--text-h)]">Welcome to BrowserBot</h2>
              <p className="text-gray-500 max-w-xl">
                Convert linear Playwright browser recordings into self-healing, fully secure Model Context Protocol (MCP) server tools for Claude Desktop.
              </p>
            </div>

            {/* Grid Layout: Start Recording vs History */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {/* Record Panel */}
              <div className="md:col-span-1 border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm space-y-6">
                <div className="space-y-1 text-left">
                  <h3 className="font-semibold text-lg text-[var(--text-h)]">New Recording</h3>
                  <p className="text-xs text-gray-400">Start recording a workflow live in Playwright</p>
                </div>

                <form onSubmit={handleStartRecording} className="space-y-4 text-left">
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-gray-500">Target Website URL</label>
                    <input
                      type="url"
                      placeholder="https://example.com"
                      value={recordUrl}
                      onChange={(e) => setRecordUrl(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-gray-50 dark:bg-gray-800 text-[var(--text-h)] focus:outline-none focus:ring-2 focus:ring-purple-500/20"
                    />
                  </div>

                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-gray-500">Workflow Description / Hint</label>
                    <input
                      type="text"
                      placeholder="e.g. Search order details"
                      value={recordHint}
                      onChange={(e) => setRecordHint(e.target.value)}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-gray-50 dark:bg-gray-800 text-[var(--text-h)] focus:outline-none focus:ring-2 focus:ring-purple-500/20"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full py-2.5 px-4 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium flex items-center justify-center space-x-2 transition cursor-pointer shadow-md shadow-purple-500/10"
                  >
                    {loading ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        <span>Launch Recorder</span>
                      </>
                    )}
                  </button>
                </form>
              </div>

              {/* History Panel */}
              <div className="md:col-span-2 border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <div className="text-left">
                    <h3 className="font-semibold text-lg text-[var(--text-h)]">Recent Sessions</h3>
                    <p className="text-xs text-gray-400">Select an existing session to resume or inspect</p>
                  </div>
                  <button
                    onClick={fetchSessions}
                    className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto max-h-[350px] border border-[var(--border)] rounded-xl">
                  {sessions.length === 0 ? (
                    <div className="py-12 text-center text-gray-400 text-sm">No recorded sessions found. Start a new one!</div>
                  ) : (
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-[var(--border)]">
                          <th className="px-4 py-3 font-semibold text-gray-500">Session ID</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Stage</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Created At</th>
                          <th className="px-4 py-3"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {sessions.map((s) => (
                          <tr key={s.session_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40 transition">
                            <td className="px-4 py-3 font-mono font-medium text-[var(--text-h)]">{s.session_id}</td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                  s.stage === "registered"
                                    ? "bg-green-50 text-green-700 dark:bg-green-950/20 dark:text-green-400"
                                    : s.stage === "failed"
                                    ? "bg-red-50 text-red-700 dark:bg-red-950/20 dark:text-red-400"
                                    : "bg-purple-50 text-purple-700 dark:bg-purple-950/20 dark:text-purple-400"
                                }`}
                              >
                                {s.stage}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-xs text-gray-400">
                              {new Date(s.created_at).toLocaleString()}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                onClick={() => loadSessionData(s)}
                                className="inline-flex items-center text-xs font-semibold text-purple-600 hover:text-purple-700 dark:text-purple-400 cursor-pointer"
                              >
                                <span>Open</span>
                                <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* Wizard Stage Flow */
          <div className="space-y-8 animate-fade-in">
            {/* Stepper progress bar */}
            <div className="border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm flex items-center justify-between">
              {[
                { step: 1, label: "Record" },
                { step: 2, label: "Confirm Parameters" },
                { step: 3, label: "Generate & Validate" },
                { step: 4, label: "Build & Install" },
              ].map((s) => {
                const isActive = currentStep === s.step;
                const isCompleted = currentStep > s.step;
                return (
                  <div key={s.step} className="flex-1 flex items-center">
                    <div className="flex items-center space-x-3">
                      <div
                        className={`w-8 h-8 rounded-lg flex items-center justify-center font-semibold text-sm transition-all duration-300 ${
                          isCompleted
                            ? "bg-green-600 text-white"
                            : isActive
                            ? "bg-purple-600 text-white ring-4 ring-purple-500/20"
                            : "bg-gray-100 dark:bg-gray-800 text-gray-400"
                        }`}
                      >
                        {isCompleted ? <Check className="w-4 h-4" /> : s.step}
                      </div>
                      <span
                        className={`text-sm font-medium ${
                          isActive ? "text-[var(--text-h)] font-semibold" : "text-gray-400"
                        }`}
                      >
                        {s.label}
                      </span>
                    </div>
                    {s.step < 4 && <div className="flex-1 mx-4 h-px bg-[var(--border)]" />}
                  </div>
                );
              })}
            </div>

            {/* Stage content */}
            {selectedSession.stage === "recording" && (
              <div className="border border-[var(--border)] rounded-2xl p-8 bg-white dark:bg-gray-900 shadow-sm text-center space-y-6">
                <div className="w-16 h-16 mx-auto rounded-2xl bg-purple-50 dark:bg-purple-950/20 flex items-center justify-center text-purple-600">
                  <Play className="w-8 h-8 animate-pulse" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-2xl font-semibold text-[var(--text-h)]">Live Recording Active</h3>
                  <p className="text-sm text-gray-500 max-w-md mx-auto">
                    The Playwright Codegen browser has launched on your local desktop. Perform your target workflow in the browser window, then close the browser window when finished.
                  </p>
                </div>
                <div className="inline-flex items-center space-x-2 text-xs font-semibold text-purple-600 bg-purple-50 dark:bg-purple-950/20 px-3 py-1.5 rounded-lg">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Waiting for browser window to close...</span>
                </div>
              </div>
            )}

            {(selectedSession.stage === "recorded" || selectedSession.stage === "extracted") && (
              <div className="border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm space-y-6">
                <div className="flex items-center justify-between">
                  <div className="text-left">
                    <h3 className="font-semibold text-xl text-[var(--text-h)]">Parameter Confirmation</h3>
                    <p className="text-xs text-gray-400">Confirm, edit, or customize parameters before code compile.</p>
                  </div>
                  <button
                    onClick={() => setShowAddParam(true)}
                    className="py-1.5 px-3 rounded-lg border border-purple-200 dark:border-purple-900 hover:bg-purple-50 dark:hover:bg-purple-950/20 text-purple-600 dark:text-purple-400 font-medium text-sm flex items-center space-x-1.5 transition cursor-pointer"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Add Parameter</span>
                  </button>
                </div>

                {/* Add Parameter Form Modal */}
                {showAddParam && (
                  <div className="p-4 border border-purple-100 dark:border-purple-950 bg-purple-50/20 dark:bg-purple-950/10 rounded-xl space-y-4 text-left animate-slide-in">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-semibold text-purple-700 dark:text-purple-400">Add New Parameter</span>
                      <button onClick={() => setShowAddParam(false)} className="text-gray-400 hover:text-gray-600">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-500">Name (snake_case)</label>
                        <input
                          type="text"
                          placeholder="e.g. tracking_id"
                          value={newParam.name}
                          onChange={(e) => setNewParam({ ...newParam, name: e.target.value })}
                          className="w-full px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-white dark:bg-gray-800 text-[var(--text-h)] focus:outline-none"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-500">Example Value</label>
                        <input
                          type="text"
                          placeholder="e.g. NBC-123"
                          value={newParam.example_value}
                          onChange={(e) => setNewParam({ ...newParam, example_value: e.target.value })}
                          className="w-full px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-white dark:bg-gray-800 text-[var(--text-h)] focus:outline-none"
                        />
                      </div>
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-gray-500">Description</label>
                      <input
                        type="text"
                        placeholder="Parameter description..."
                        value={newParam.description}
                        onChange={(e) => setNewParam({ ...newParam, description: e.target.value })}
                        className="w-full px-3 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-white dark:bg-gray-800 text-[var(--text-h)] focus:outline-none"
                      />
                    </div>
                    <div className="flex items-center space-x-6">
                      <label className="flex items-center space-x-2 text-sm text-[var(--text-h)]">
                        <input
                          type="checkbox"
                          checked={newParam.is_sensitive}
                          onChange={(e) => setNewParam({ ...newParam, is_sensitive: e.target.checked })}
                          className="rounded text-purple-600 focus:ring-purple-500/20"
                        />
                        <span>Is Sensitive (Password)</span>
                      </label>
                      <label className="flex items-center space-x-2 text-sm text-[var(--text-h)]">
                        <input
                          type="checkbox"
                          checked={newParam.is_optional}
                          onChange={(e) => setNewParam({ ...newParam, is_optional: e.target.checked })}
                          className="rounded text-purple-600 focus:ring-purple-500/20"
                        />
                        <span>Is Optional</span>
                      </label>
                    </div>
                    <button
                      onClick={handleAddManualParam}
                      className="py-1.5 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition cursor-pointer"
                    >
                      Add Parameter
                    </button>
                  </div>
                )}

                {/* Parameters table */}
                <div className="border border-[var(--border)] rounded-xl overflow-hidden">
                  {parameters.length === 0 ? (
                    <div className="py-8 text-center text-gray-400 text-sm">No parameters extracted or added. Add one above!</div>
                  ) : (
                    <table className="w-full text-left text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-50 dark:bg-gray-800/50 border-b border-[var(--border)]">
                          <th className="px-4 py-3 font-semibold text-gray-500 w-12">Enable</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Name</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Example Value</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Sensitive</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Optional</th>
                          <th className="px-4 py-3 font-semibold text-gray-500">Description</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[var(--border)]">
                        {parameters.map((p, idx) => (
                          <tr
                            key={idx}
                            className={`transition ${
                              p.enabled ? "hover:bg-gray-50 dark:hover:bg-gray-800/40" : "opacity-50 bg-gray-50/50 dark:bg-gray-900/50"
                            }`}
                          >
                            <td className="px-4 py-3 text-center">
                              <input
                                type="checkbox"
                                checked={p.enabled}
                                onChange={(e) => handleParamChange(idx, "enabled", e.target.checked)}
                                className="rounded text-purple-600 focus:ring-purple-500/20"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <div className="space-y-1">
                                <input
                                  type="text"
                                  value={p.name}
                                  disabled={!p.enabled}
                                  onChange={(e) => handleParamChange(idx, "name", e.target.value)}
                                  className={`w-full px-2 py-1 text-xs rounded border border-[var(--border)] bg-transparent font-mono text-[var(--text-h)] focus:outline-none focus:ring-1 focus:ring-purple-500/20 ${
                                    paramErrors[idx] ? "border-red-500" : ""
                                  }`}
                                />
                                {paramErrors[idx] && <p className="text-[10px] text-red-500 m-0">{paramErrors[idx]}</p>}
                              </div>
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="text"
                                value={p.example_value}
                                disabled={!p.enabled}
                                onChange={(e) => handleParamChange(idx, "example_value", e.target.value)}
                                className="w-full px-2 py-1 text-xs rounded border border-[var(--border)] bg-transparent text-[var(--text-h)] focus:outline-none"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="checkbox"
                                checked={p.is_sensitive}
                                disabled={!p.enabled}
                                onChange={(e) => handleParamChange(idx, "is_sensitive", e.target.checked)}
                                className="rounded text-purple-600"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="checkbox"
                                checked={p.is_optional}
                                disabled={!p.enabled}
                                onChange={(e) => handleParamChange(idx, "is_optional", e.target.checked)}
                                className="rounded text-purple-600"
                              />
                            </td>
                            <td className="px-4 py-3">
                              <input
                                type="text"
                                value={p.description || ""}
                                disabled={!p.enabled}
                                onChange={(e) => handleParamChange(idx, "description", e.target.value)}
                                className="w-full px-2 py-1 text-xs rounded border border-[var(--border)] bg-transparent text-gray-500 focus:outline-none"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                <div className="flex justify-end pt-4 border-t border-[var(--border)]">
                  <button
                    onClick={handleConfirmParameters}
                    disabled={loading}
                    className="py-2.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium flex items-center space-x-2 transition cursor-pointer shadow-md shadow-purple-500/10"
                  >
                    <span>Confirm & Continue</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {(selectedSession.stage === "confirmed" || selectedSession.stage === "generated" || selectedSession.stage === "failed") && (
              <div className="border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm space-y-6">
                <div className="text-left space-y-1">
                  <h3 className="font-semibold text-xl text-[var(--text-h)]">Generate & Validate</h3>
                  <p className="text-xs text-gray-400">Compile Playwright automation script and execute offline validator checks.</p>
                </div>

                {/* Compilation progress or results view */}
                {!validationReport ? (
                  <div className="py-12 border-2 border-dashed border-[var(--border)] rounded-2xl flex flex-col items-center justify-center space-y-4">
                    <div className="w-12 h-12 rounded-xl bg-purple-50 dark:bg-purple-950/20 flex items-center justify-center text-purple-600">
                      <Terminal className="w-6 h-6" />
                    </div>
                    <div className="space-y-1 text-center">
                      <h4 className="font-medium text-[var(--text-h)]">Ready to Compile</h4>
                      <p className="text-xs text-gray-400">Click compile to run code generation and sandboxed validation trials.</p>
                    </div>
                    <button
                      onClick={handleGenerateCode}
                      disabled={loading}
                      className="py-2.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium flex items-center space-x-2 transition cursor-pointer"
                    >
                      {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <span>Compile & Validate</span>}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-6 animate-fade-in text-left">
                    <div className="flex items-center justify-between p-4 rounded-xl border bg-gray-50 dark:bg-gray-800/40 border-[var(--border)]">
                      <div>
                        <h4 className="font-semibold text-[var(--text-h)]">Validation Run Complete</h4>
                        <p className="text-xs text-gray-400">Status details and compliance metrics.</p>
                      </div>
                      <span
                        className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold ${
                          validationReport.overall_success
                            ? "bg-green-100 text-green-700 dark:bg-green-950/20 dark:text-green-400"
                            : "bg-red-100 text-red-700 dark:bg-red-950/20 dark:text-red-400"
                        }`}
                      >
                        {validationReport.overall_success ? (
                          <>
                            <CheckCircle2 className="w-4 h-4 mr-1.5" />
                            <span>Passed</span>
                          </>
                        ) : (
                          <>
                            <ShieldAlert className="w-4 h-4 mr-1.5" />
                            <span>Failed</span>
                          </>
                        )}
                      </span>
                    </div>

                    {/* Stage breakdown */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {[
                        { title: "Script existence", status: validationReport.file_existence },
                        { title: "Syntax compilation", status: validationReport.compilation },
                        { title: "FastMCP module imports", status: validationReport.import_check },
                        { title: "Runtime dry-run trial", status: validationReport.runtime_dry_run },
                      ].map((stage, sIdx) => (
                        <div
                          key={sIdx}
                          className="p-4 rounded-xl border border-[var(--border)] flex items-center justify-between"
                        >
                          <span className="text-sm font-medium text-[var(--text-h)]">{stage.title}</span>
                          {stage.status?.success ? (
                            <Check className="w-4 h-4 text-green-600" />
                          ) : (
                            <X className="w-4 h-4 text-red-600" />
                          )}
                        </div>
                      ))}
                    </div>

                    {/* Retry details if failed */}
                    {!validationReport.overall_success && (
                      <div className="p-4 bg-red-50/50 dark:bg-red-950/10 border border-red-200 dark:border-red-950 rounded-xl space-y-3">
                        <span className="text-sm font-semibold text-red-700 dark:text-red-400 flex items-center space-x-1.5">
                          <AlertCircle className="w-4 h-4" />
                          <span>Validation Failures Detected</span>
                        </span>
                        <pre className="text-xs font-mono bg-white dark:bg-gray-900 border border-red-100 dark:border-red-950/50 p-3 rounded-lg overflow-x-auto text-red-600">
                          {validationReport.runtime_dry_run?.message || "Verify logs for details."}
                        </pre>
                        <button
                          onClick={handleGenerateCode}
                          disabled={loading}
                          className="py-1.5 px-4 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition cursor-pointer"
                        >
                          Retry Generator Loop
                        </button>
                      </div>
                    )}

                    {validationReport.overall_success && (
                      <div className="flex justify-end pt-4 border-t border-[var(--border)]">
                        <button
                          onClick={handlePackageTool}
                          disabled={loading}
                          className="py-2.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium flex items-center space-x-2 transition cursor-pointer shadow-md shadow-purple-500/10"
                        >
                          <span>Proceed to Install</span>
                          <ChevronRight className="w-4 h-4" />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {(selectedSession.stage === "packaged" || selectedSession.stage === "registered") && (
              <div className="border border-[var(--border)] rounded-2xl p-6 bg-white dark:bg-gray-900 shadow-sm space-y-6">
                <div className="text-left space-y-1">
                  <h3 className="font-semibold text-xl text-[var(--text-h)]">Build & Install</h3>
                  <p className="text-xs text-gray-400">Compile package and register with your local Claude Desktop config.</p>
                </div>

                {!registrationConfig || Object.keys(registrationConfig).length === 0 ? (
                  <div className="py-12 border-2 border-dashed border-[var(--border)] rounded-2xl flex flex-col items-center justify-center space-y-4">
                    <div className="w-12 h-12 rounded-xl bg-purple-50 dark:bg-purple-950/20 flex items-center justify-center text-purple-600">
                      <Settings className="w-6 h-6" />
                    </div>
                    <div className="space-y-1 text-center">
                      <h4 className="font-medium text-[var(--text-h)]">Tool Compiled Successfully</h4>
                      <p className="text-xs text-gray-400">Deploy build package structure and finalize setup.</p>
                    </div>
                    <button
                      onClick={handleRegisterPackage}
                      disabled={loading}
                      className="py-2.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white font-medium flex items-center space-x-2 transition cursor-pointer"
                    >
                      {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <span>Register with Claude Desktop</span>}
                    </button>
                  </div>
                ) : (
                  <div className="space-y-6 animate-fade-in text-left">
                    <div className="p-6 bg-green-50/50 dark:bg-green-950/10 border border-green-200 dark:border-green-950 rounded-2xl flex items-start space-x-4">
                      <div className="w-10 h-10 rounded-lg bg-green-100 dark:bg-green-950/30 flex items-center justify-center text-green-600">
                        <Check className="w-5 h-5" />
                      </div>
                      <div className="space-y-1 flex-1">
                        <h4 className="font-semibold text-green-800 dark:text-green-400">MCP Tool Successfully Installed!</h4>
                        <p className="text-sm text-green-700/80 dark:text-green-500/80">
                          Your server config is merged. Please **restart Claude Desktop** completely to load the new tool.
                        </p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Claude Desktop config snippet</label>
                      <pre className="text-xs font-mono bg-gray-50 dark:bg-gray-800 p-4 border border-[var(--border)] rounded-xl overflow-x-auto text-[var(--text-h)]">
                        {JSON.stringify(registrationConfig, null, 2)}
                      </pre>
                    </div>

                    <div className="flex justify-end pt-4 border-t border-[var(--border)]">
                      <button
                        onClick={resetWizard}
                        className="py-2.5 px-6 rounded-xl bg-purple-600 hover:bg-purple-700 text-white font-medium transition cursor-pointer shadow-md shadow-purple-500/10"
                      >
                        Back to Dashboard
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
