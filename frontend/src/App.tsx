import { useState, useEffect, useRef } from "react";
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
  ChevronUp,
  ChevronDown,
  Trash2,
  Clock,
  AlertTriangle,
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

  // Live WebSocket Stage-Events Streaming States
  const [liveEvents, setLiveEvents] = useState<any[]>([]);
  const [failureScreenshot, setFailureScreenshot] = useState<string | null>(null);

  // Helper to fetch latest stage status from event list
  const getStageStatus = (stageName: string) => {
    const matching = liveEvents.filter((e) => e.stage === stageName);
    if (matching.length === 0) return { status: "pending", message: "Waiting to start..." };
    return matching[matching.length - 1];
  };

  // Developer Console Drawer States
  const [isConsoleOpen, setIsConsoleOpen] = useState(false);
  const [consoleLogs, setConsoleLogs] = useState<string[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [consoleHeight, setConsoleHeight] = useState(240);
  const [isResizing, setIsResizing] = useState(false);
  const [duration, setDuration] = useState(0);
  const [isScrollPaused, setIsScrollPaused] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);

  // Subscribe to SSE logs for the selected session
  useEffect(() => {
    if (!selectedSession) {
      setConsoleLogs([]);
      setDuration(0);
      setIsScrollPaused(false);
      return;
    }

    setConsoleLogs([]);
    setDuration(0);
    setIsScrollPaused(false);

    const eventSource = new EventSource(api.getLogsUrl(selectedSession.session_id));
    
    eventSource.onmessage = (event) => {
      const data = event.data;
      if (data) {
        setConsoleLogs((prev) => [...prev, data]);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE logs stream connection error, closing...", err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [selectedSession?.session_id]);

  // Subscribe to WebSocket stage events for the selected session
  useEffect(() => {
    if (!selectedSession?.session_id) {
      setLiveEvents([]);
      setFailureScreenshot(null);
      return;
    }

    setLiveEvents([]);
    setFailureScreenshot(null);

    // Compute ws url dynamically mapping protocol and host
    const logsUrl = api.getLogsUrl(selectedSession.session_id);
    const url = new URL(logsUrl);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.pathname = `/sessions/ws/sessions/${selectedSession.session_id}`;
    const wsUrl = url.toString();

    console.log("Connecting to WebSocket event stream:", wsUrl);
    const socket = new WebSocket(wsUrl);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload) {
          setLiveEvents((prev) => {
            // Keep unique events by stage and status to avoid duplication
            const filtered = prev.filter(
              (e) => !(e.stage === payload.stage && e.status === payload.status)
            );
            return [...filtered, payload];
          });

          // Check if metadata contains base64 encoded screenshot on validation failure
          if (payload.metadata && payload.metadata.screenshot) {
            setFailureScreenshot(payload.metadata.screenshot);
          }
        }
      } catch (err) {
        console.error("Failed to parse stage event websocket message", err);
      }
    };

    socket.onerror = (err) => {
      console.error("WebSocket stage events stream error", err);
    };

    socket.onclose = () => {
      console.log("WebSocket stage events stream closed");
    };

    return () => {
      socket.close();
    };
  }, [selectedSession?.session_id]);

  // Track session timer duration
  useEffect(() => {
    let interval: any;
    const activeStages = ["recording", "extracting", "confirming", "generating", "packaging"];
    if (selectedSession && activeStages.includes(selectedSession.stage)) {
      interval = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } else {
      setDuration(0);
    }
    return () => clearInterval(interval);
  }, [selectedSession?.stage, selectedSession?.session_id]);

  // Auto-expand logs drawer on error (height 300px per Design Brief Sec 7)
  useEffect(() => {
    if (selectedSession?.stage === "failed" || (validationReport && !validationReport.overall_success)) {
      setIsConsoleOpen(true);
      setConsoleHeight(300);
    }
  }, [selectedSession?.stage, validationReport]);

  // Handle vertical resizing of log drawer (clamped 150px - 500px per Design Brief Sec 8)
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newHeight = window.innerHeight - e.clientY;
      if (newHeight >= 150 && newHeight <= 500) {
        setConsoleHeight(newHeight);
      }
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isResizing]);

  // Auto-scroll logs list
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [consoleLogs, autoScroll]);

  // Toggle console drawer via Ctrl + \
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "\\") {
        e.preventDefault();
        setIsConsoleOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 15;
    if (isAtBottom) {
      setAutoScroll(true);
      setIsScrollPaused(false);
    } else {
      setAutoScroll(false);
      setIsScrollPaused(true);
    }
  };

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
    setLiveEvents([]);
    setFailureScreenshot(null);
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
                  loading ? (
                    <div className="space-y-6 text-left animate-fade-in">
                      <div className="flex items-center space-x-3 p-4 bg-purple-50/50 dark:bg-purple-950/10 border border-purple-200 dark:border-purple-950/50 rounded-xl">
                        <RefreshCw className="w-5 h-5 animate-spin text-purple-600" />
                        <div>
                          <h4 className="font-semibold text-[var(--text-h)]">Compiling & Validating</h4>
                          <p className="text-xs text-gray-400">Executing verification pipeline stages in real-time...</p>
                        </div>
                      </div>

                      <div className="space-y-3">
                        {[
                          { id: "stage_5_file_existence", label: "Check generated files existence" },
                          { id: "stage_5_compilation", label: "Python syntax compilation" },
                          { id: "stage_5_import_check", label: "FastMCP module imports" },
                          { id: "stage_5_runtime_dry_run", label: "Runtime dry-run trial execution" },
                        ].map((stage, idx) => {
                          const ev = getStageStatus(stage.id);
                          return (
                            <div
                              key={idx}
                              className="p-4 rounded-xl border border-[var(--border)] bg-gray-50/30 dark:bg-gray-800/10 flex items-center justify-between transition"
                            >
                              <div className="space-y-1">
                                <span className="text-sm font-medium text-[var(--text-h)] block">{stage.label}</span>
                                <span className="text-xs text-gray-400 block">{ev.message}</span>
                              </div>
                              <div className="flex items-center">
                                {ev.status === "in_progress" && (
                                  <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                                )}
                                {ev.status === "success" && (
                                  <Check className="w-4 h-4 text-green-600" />
                                )}
                                {ev.status === "failed" && (
                                  <X className="w-4 h-4 text-red-600" />
                                )}
                                {ev.status === "skipped" && (
                                  <Clock className="w-4 h-4 text-gray-400" />
                                )}
                                {ev.status === "pending" && (
                                  <Clock className="w-4 h-4 text-gray-300" />
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : (
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
                        <span>Compile & Validate</span>
                      </button>
                    </div>
                  )
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

                    {/* Failure diagnostic screenshot */}
                    {failureScreenshot && (
                      <div className="space-y-2">
                        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider block">Sandbox Execution Failure Screenshot</span>
                        <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-gray-50 dark:bg-gray-800">
                          <img
                            src={`data:image/png;base64,${failureScreenshot}`}
                            alt="Failure diagnostic screenshot"
                            className="w-full h-auto object-contain max-h-[300px] border-b border-[var(--border)]"
                          />
                          <div className="p-3 text-xs text-gray-400 bg-white dark:bg-gray-900 flex justify-between items-center">
                            <span>Captured automatically during failed dry-run trial.</span>
                            <button
                              onClick={() => {
                                const newTab = window.open();
                                if (newTab) {
                                  newTab.document.write(`<img src="data:image/png;base64,${failureScreenshot}" style="max-width:100%; height:auto;" />`);
                                }
                              }}
                              className="text-purple-600 hover:text-purple-700 font-medium transition cursor-pointer"
                            >
                              View Fullscreen
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Failure diagnostics — shown when any stage fails */}
                    {!validationReport.overall_success && (() => {
                      // Determine which stages failed to show per-stage diagnostics
                      const stageDetails = [
                        { key: "file_existence", label: "Script Existence", data: validationReport.file_existence },
                        { key: "compilation", label: "Syntax Compilation", data: validationReport.compilation },
                        { key: "import_check", label: "FastMCP Imports", data: validationReport.import_check },
                        { key: "runtime_dry_run", label: "Runtime Dry-Run", data: validationReport.runtime_dry_run },
                      ];
                      const failedStages = stageDetails.filter(s => !s.data?.success);
                      const passedStages = stageDetails.filter(s => s.data?.success);
                      const isPartialFailure = passedStages.length > 0 && failedStages.length > 0;

                      return (
                        <div className="space-y-3">
                          {/* Header row — warning vs full failure */}
                          <div className={`flex items-start space-x-2.5 p-3 rounded-xl border ${
                            isPartialFailure
                              ? "bg-amber-50/60 dark:bg-amber-950/10 border-amber-200 dark:border-amber-900/50"
                              : "bg-red-50/50 dark:bg-red-950/10 border-red-200 dark:border-red-950"
                          }`}>
                            {isPartialFailure
                              ? <AlertTriangle className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
                              : <AlertCircle className="w-4 h-4 text-red-600 mt-0.5 shrink-0" />
                            }
                            <div>
                              <p className={`text-sm font-semibold ${isPartialFailure ? "text-amber-700 dark:text-amber-400" : "text-red-700 dark:text-red-400"}`}>
                                {isPartialFailure
                                  ? `Partial Failure — ${passedStages.length} of 4 stages passed`
                                  : "Validation Failed — All stages could not be completed"}
                              </p>
                              <p className="text-xs text-gray-500 mt-0.5">
                                Review the failing stage below and follow the suggested recovery action.
                              </p>
                            </div>
                          </div>

                          {/* Per-stage failure detail */}
                          {failedStages.map((stage, idx) => (
                            <div key={idx} className="border border-red-100 dark:border-red-950/50 rounded-xl overflow-hidden">
                              <div className="flex items-center justify-between px-4 py-2.5 bg-red-50/40 dark:bg-red-950/10 border-b border-red-100 dark:border-red-950/50">
                                <div className="flex items-center space-x-2">
                                  <X className="w-3.5 h-3.5 text-red-500" />
                                  <span className="text-xs font-semibold text-red-700 dark:text-red-400 uppercase tracking-wider">{stage.label}</span>
                                </div>
                                <span className="text-xs text-red-400 font-mono">FAILED</span>
                              </div>
                              {stage.data?.message && (
                                <div className="p-3 bg-white dark:bg-gray-900">
                                  <pre className="text-xs font-mono text-red-600 dark:text-red-400 whitespace-pre-wrap break-words leading-relaxed">
                                    {stage.data.message}
                                  </pre>
                                </div>
                              )}
                            </div>
                          ))}

                          {/* Recovery actions */}
                          <div className="flex items-center justify-between pt-1">
                            <p className="text-xs text-gray-400">
                              {failedStages.some(s => s.key === "runtime_dry_run")
                                ? "The dry-run failed. Check the console logs or try regenerating."
                                : failedStages.some(s => s.key === "compilation" || s.key === "import_check")
                                ? "Code generation produced invalid Python. Retry to attempt a self-corrected run."
                                : "Verify the recorded session has valid actions, then retry."}
                            </p>
                            <button
                              onClick={handleGenerateCode}
                              disabled={loading}
                              className="py-1.5 px-4 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium transition cursor-pointer shrink-0 ml-4 disabled:opacity-50"
                            >
                              Retry Generator Loop
                            </button>
                          </div>
                        </div>
                      );
                    })()}

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

      {/* Developer Console Drawer Component */}
      {selectedSession && (
        <div 
          className="console-drawer border-t border-[var(--border)] bg-[var(--bg)] text-[var(--text)] transition-all duration-200 select-none flex flex-col w-full relative"
          style={{ height: isConsoleOpen ? `${consoleHeight}px` : "36px" }}
        >
          {/* Resize Handle (only visible when expanded) */}
          {isConsoleOpen && (
            <div 
              className="console-resizer h-1 cursor-ns-resize hover:bg-[var(--accent)] transition-colors w-full absolute top-0 left-0 right-0 z-50"
              onMouseDown={(e) => {
                e.preventDefault();
                setIsResizing(true);
              }}
            />
          )}
          
          {/* Header Panel */}
          <div 
            className="console-header flex items-center justify-between px-4 h-8 border-b border-[var(--border)] select-none cursor-pointer text-xs font-medium text-[var(--text)] bg-[var(--bg)] hover:text-[var(--text-h)] transition-colors w-full"
            onClick={() => setIsConsoleOpen(!isConsoleOpen)}
          >
            <div className="flex items-center space-x-4">
              <span className="flex items-center space-x-1.5 font-semibold text-[var(--text-h)]">
                <Terminal className="w-3.5 h-3.5 text-[var(--text)]" />
                <span>Console</span>
              </span>
              
              {/* Counters */}
              <div className="flex items-center space-x-2 text-[10px]" onClick={(e) => e.stopPropagation()}>
                {consoleLogs.filter(line => line.includes("[ERROR]")).length > 0 && (
                  <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded border border-red-500/30 bg-red-500/5 text-red-600 dark:text-red-400 font-mono">
                    <AlertCircle className="w-2.5 h-2.5" />
                    <span>{consoleLogs.filter(line => line.includes("[ERROR]")).length}</span>
                  </span>
                )}
                {consoleLogs.filter(line => line.includes("[WARNING]")).length > 0 && (
                  <span className="flex items-center space-x-1 px-1.5 py-0.5 rounded border border-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400 font-mono">
                    <AlertTriangle className="w-2.5 h-2.5" />
                    <span>{consoleLogs.filter(line => line.includes("[WARNING]")).length}</span>
                  </span>
                )}
                {consoleLogs.length > 0 && (
                  <span className="text-[var(--text)] font-mono">
                    {consoleLogs.length} logs
                  </span>
                )}
              </div>

              {/* Status Badge */}
              <div className="flex items-center space-x-1.5 text-[10px] text-[var(--text)] font-mono" onClick={(e) => e.stopPropagation()}>
                <span className={`w-1.5 h-1.5 rounded-full ${
                  selectedSession.stage === "failed" ? "bg-red-500 animate-pulse" :
                  ["recording", "extracting", "confirming", "generating", "packaging"].includes(selectedSession.stage) ? "bg-[var(--accent)] animate-pulse" :
                  "bg-green-500"
                }`} />
                <span className="capitalize">{selectedSession.stage}</span>
              </div>

              {/* Execution Duration */}
              {duration > 0 && (
                <span className="flex items-center space-x-1 text-[10px] text-[var(--text)] font-mono" onClick={(e) => e.stopPropagation()}>
                  <Clock className="w-3 h-3 text-[var(--text)]" />
                  <span>{duration}s</span>
                </span>
              )}
            </div>
            
            {/* Console controls */}
            <div className="flex items-center space-x-3" onClick={(e) => e.stopPropagation()}>
              {isConsoleOpen && (
                <>
                  {/* Auto-Scroll Toggle */}
                  <label className="flex items-center space-x-1.5 cursor-pointer text-[var(--text)] hover:text-[var(--text-h)] text-[10px] font-mono select-none">
                    <input 
                      type="checkbox" 
                      checked={autoScroll}
                      onChange={(e) => {
                        setAutoScroll(e.target.checked);
                        if (e.target.checked) setIsScrollPaused(false);
                      }}
                      className="rounded border-[var(--border)] bg-transparent text-[var(--accent)] focus:ring-[var(--accent)]/20 w-3 h-3 cursor-pointer"
                    />
                    <span>Auto-scroll</span>
                  </label>
                  
                  {/* Clear logs */}
                  <button 
                    onClick={() => {
                      setConsoleLogs([]);
                      setIsScrollPaused(false);
                    }}
                    className="p-1 text-[var(--text)] hover:text-red-500 rounded transition-colors cursor-pointer"
                    title="Clear Console"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </>
              )}
              
              {/* Toggle Expand Icon */}
              <button 
                onClick={() => setIsConsoleOpen(!isConsoleOpen)}
                className="p-1 text-[var(--text)] hover:text-[var(--text-h)] rounded transition-colors cursor-pointer"
              >
                {isConsoleOpen ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronUp className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
          
          {/* Logs Terminal Area */}
          {isConsoleOpen && (
            <div className="flex-1 min-h-0 relative flex flex-col bg-[var(--code-bg)]">
              <div 
                ref={scrollRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-normal select-text select-all whitespace-pre-wrap text-left space-y-1.5 scrollbar-thin w-full text-[var(--text-h)]"
              >
                {consoleLogs.length === 0 ? (
                  <div className="text-[var(--text)] opacity-60 italic py-2 px-1">Console is clear. Telemetry inactive.</div>
                ) : (
                  consoleLogs.map((logLine, idx) => {
                    // Determine line color and styles based on keywords
                    let colorClass = "text-[var(--text)] opacity-80";
                    if (logLine.includes("[ERROR]")) {
                      colorClass = "text-red-600 dark:text-red-400 font-semibold";
                    } else if (logLine.includes("[WARNING]")) {
                      colorClass = "text-amber-600 dark:text-amber-400";
                    } else if (logLine.includes("[SUCCESS]") || logLine.includes("completed successfully") || logLine.includes("passed") || logLine.includes("[INFO] Console initialized")) {
                      colorClass = "text-green-600 dark:text-green-400";
                    } else if (logLine.includes("[INFO]")) {
                      colorClass = "text-[var(--text-h)] opacity-90";
                    }
                    
                    // Parse timestamp and format nicely if present
                    const timestampMatch = logLine.match(/^\[(\d{2}:\d{2}:\d{2})\]/);
                    if (timestampMatch) {
                      const time = timestampMatch[1];
                      const content = logLine.substring(time.length + 2).trim();
                      return (
                        <div key={idx} className="flex items-start py-0.5 border-b border-[var(--border)]/10 hover:bg-[var(--border)]/20 font-mono">
                          <span className="text-[var(--text)] opacity-40 mr-3 flex-shrink-0 select-none">{time}</span>
                          <span className={`flex-1 break-all ${colorClass}`}>{content}</span>
                        </div>
                      );
                    }
                    
                    return (
                      <div key={idx} className={`py-0.5 break-all font-mono ${colorClass}`}>
                        {logLine}
                      </div>
                    );
                  })
                )}
              </div>
              
              {/* Resume Auto-scroll Banner */}
              {isScrollPaused && (
                <button 
                  onClick={() => {
                    setAutoScroll(true);
                    setIsScrollPaused(false);
                    if (scrollRef.current) {
                      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                    }
                  }}
                  className="absolute bottom-4 left-1/2 -translate-x-1/2 px-3 py-1.5 bg-[var(--bg)] border border-[var(--border)] text-[10px] text-[var(--text-h)] font-mono rounded-md hover:bg-[var(--code-bg)] transition-colors cursor-pointer shadow-sm z-50 flex items-center space-x-1.5"
                >
                  <RefreshCw className="w-3 h-3 animate-spin text-[var(--text)]" />
                  <span>Resume Auto-scroll</span>
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
