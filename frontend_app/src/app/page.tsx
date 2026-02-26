'use client';
import { useState, useEffect } from 'react';

export default function Settings() {
    const [status, setStatus] = useState<any>(null);
    const [engineState, setEngineState] = useState('Standby');
    const [engineLogs, setEngineLogs] = useState<string[]>([]);
    const [dbPath, setDbPath] = useState('');
    const [watchFolders, setWatchFolders] = useState<string[]>([]);
    const [models, setModels] = useState<any[]>([]);
    const [selectedModel, setSelectedModel] = useState<string>('models/gemini-3.1-flash');
    const [saving, setSaving] = useState(false);
    const [transcribeProgress, setTranscribeProgress] = useState<{ done: number, total: number, filename: string } | null>(null);
    const [isTranscribing, setIsTranscribing] = useState(false);

    // Archive-wide duplicate scanner
    const [duplicateGroups, setDuplicateGroups] = useState<any[]>([]);
    const [showDuplicates, setShowDuplicates] = useState(false);
    const [loadingDupes, setLoadingDupes] = useState(false);

    useEffect(() => {
        fetch('http://localhost:8000/api/status')
            .then(res => res.json())
            .then(data => setStatus(data))
            .catch(err => setStatus({ status: 'offline' }));

        fetch('http://localhost:8000/api/models')
            .then(res => res.json())
            .then(data => setModels(data))
            .catch(err => console.error(err));

        fetch('http://localhost:8000/api/settings')
            .then(res => res.json())
            .then(data => {
                if (data.geminiModel) setSelectedModel(data.geminiModel);
                if (data.dbPath) setDbPath(data.dbPath);

                // Load saved watch folders, fallback to the default input state
                if (data.watchFolders && data.watchFolders.length > 0) {
                    setWatchFolders(data.watchFolders);
                } else {
                    setWatchFolders(['/Volumes/X9 Pro/']);
                }
            })
            .catch(err => console.error(err));
    }, []);

    // Live Engine Logs Poller
    useEffect(() => {
        let interval: NodeJS.Timeout;
        const isActive = engineState.includes('Background') || engineState.includes('Scanning');

        if (isActive) {
            // Fetch immediately, then poll
            const fetchLogs = () => {
                fetch(`http://localhost:8000/api/engine/logs?limit=8&t=${Date.now()}`, { cache: 'no-store' })
                    .then(res => res.json())
                    .then(data => {
                        if (data.logs) setEngineLogs(data.logs);
                    })
                    .catch(() => { });
            };

            fetchLogs();
            interval = setInterval(fetchLogs, 2000);
        }

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [engineState]);

    const handleSettingsUpdate = async (updates: any) => {
        setSaving(true);
        try {
            await fetch('http://localhost:8000/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            // Update the connection text in backend status
            if (updates.dbPath && status) {
                setStatus({ ...status, db_path: updates.dbPath });
            }
        } catch (err) {
            console.error(err);
        }
        setSaving(false);
    };

    const handleModelChange = async (e: any) => {
        const newModel = e.target.value;
        setSelectedModel(newModel);
        await handleSettingsUpdate({ geminiModel: newModel });
    };

    const handleDbPathChange = async (e: any) => {
        const newPath = e.target.value;
        setDbPath(newPath);
        await handleSettingsUpdate({ dbPath: newPath });
    };

    const updateWatchFolder = async (index: number, val: string) => {
        const newFolders = [...watchFolders];
        newFolders[index] = val;
        setWatchFolders(newFolders);
        await handleSettingsUpdate({ watchFolders: newFolders });
    };

    const addWatchFolder = () => {
        setWatchFolders([...watchFolders, ""]);
    };

    const removeWatchFolder = async (index: number) => {
        const newFolders = watchFolders.filter((_, i) => i !== index);
        setWatchFolders(newFolders);
        await handleSettingsUpdate({ watchFolders: newFolders });
    };

    const startTranscribeAll = async () => {
        if (isTranscribing) return;
        setIsTranscribing(true);
        setTranscribeProgress({ done: 0, total: 0, filename: 'Counting videos...' });
        setEngineState('Transcribing...');
        try {
            const res = await fetch('http://localhost:8000/api/engine/transcribe-all', { cache: 'no-store' });
            const reader = res.body!.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n\n');
                buffer = parts.pop() || '';
                for (const part of parts) {
                    const line = part.replace(/^data: /, '').trim();
                    if (!line) continue;
                    try {
                        const evt = JSON.parse(line);
                        setTranscribeProgress({ done: evt.done, total: evt.total, filename: evt.filename });
                        if (evt.status === 'complete') {
                            setEngineState('Transcription Complete');
                        }
                    } catch { }
                }
            }
        } catch (e) {
            setEngineState('Transcription Error');
        } finally {
            setIsTranscribing(false);
        }
    };

    const startScan = async (path: string) => {
        if (!path.trim()) return;
        setEngineState('Scanning...');
        try {
            await fetch('http://localhost:8000/api/engine/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: path })
            });
            setEngineState('Scan Started in Background');
        } catch (e) {
            setEngineState('Error starting scan');
        }
    };

    const fetchDuplicates = async () => {
        setLoadingDupes(true);
        setShowDuplicates(true);
        try {
            const res = await fetch(`http://localhost:8000/api/duplicates?t=${Date.now()}`, { cache: 'no-store' });
            const data = await res.json();
            setDuplicateGroups(data.groups || []);
        } catch (e) {
            alert('Error loading duplicates');
        }
        setLoadingDupes(false);
    };

    const deleteFromIndex = async (id: number) => {
        if (!confirm('Remove this video from the AI Director index? The original file on disk is NOT deleted.')) return;
        await fetch('http://localhost:8000/api/video/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id })
        });
        setDuplicateGroups(prev => prev.map(g => ({ ...g, clips: g.clips.filter((c: any) => c.id !== id) })).filter(g => g.clips.length > 1));
    };

    const handleDatabaseReset = async () => {
        if (!confirm('⚠️ WARNING: This will completely wipe your video archive database and logs. All indexing and transcriptions will be lost. This cannot be undone. \n\nAre you sure you want to proceed?')) return;

        try {
            const res = await fetch('http://localhost:8000/api/database/reset', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'success') {
                alert('Database has been reset. The app will now reload.');
                window.location.reload();
            } else {
                alert('Error: ' + data.message);
            }
        } catch (err) {
            console.error(err);
            alert('Failed to reset database.');
        }
    };

    return (
        <div>
            <h1 style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '32px' }}>⚙️</span>
                Settings
            </h1>
            <p className="subtitle">Monitor and control your AI Director engine.</p>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 1fr) minmax(500px, 2fr)', gap: '24px', alignItems: 'start', margin: '32px 0' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    <div className="glass-panel">
                        <div className="clip-card-header" style={{ border: 'none', padding: 0, paddingBottom: 16 }}>
                            <span style={{ color: 'var(--success)', marginRight: '8px' }}>🗄️</span>
                            Backend Status
                        </div>
                        <div style={{ fontSize: 24, fontWeight: 600, color: status?.status === 'online' ? 'var(--success)' : 'var(--danger)' }}>
                            {status ? status.status.toUpperCase() : 'LOADING...'}
                        </div>
                        {status?.db_path && (
                            <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
                                Connected to:<br />
                                <span style={{ color: 'var(--text-primary)', wordBreak: 'break-all' }}>{status.db_path}</span>
                            </div>
                        )}
                        <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                            <label style={{ display: 'block', marginBottom: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                                Database Path (Requires Restart)
                            </label>
                            <input
                                type="text"
                                value={dbPath}
                                onChange={handleDbPathChange}
                                placeholder="e.g. /Volumes/X9 Pro/Video_Archive.db"
                                style={{
                                    width: '100%',
                                    padding: '10px 12px',
                                    borderRadius: '6px',
                                    background: 'rgba(255,255,255,0.05)',
                                    border: '1px solid rgba(255,255,255,0.1)',
                                    color: 'white',
                                    outline: 'none'
                                }}
                            />
                            <p style={{ marginTop: 6, fontSize: 11, color: 'var(--text-tertiary)' }}>This is the absolute path to the main SQLite `.db` file mapping all indexes, transcripts, and model outputs.</p>
                        </div>
                    </div>

                    <div className="glass-panel">
                        <div className="clip-card-header" style={{ border: 'none', padding: 0, paddingBottom: 16 }}>
                            <span style={{ color: 'var(--accent-secondary)', marginRight: '8px' }}>🧠</span>
                            AI Configuration
                        </div>
                        <div style={{ marginBottom: 12 }}>
                            <label style={{ display: 'block', marginBottom: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                                Director Generation Model
                            </label>
                            <select
                                value={selectedModel}
                                onChange={handleModelChange}
                                style={{
                                    width: '100%',
                                    padding: '10px 12px',
                                    borderRadius: '6px',
                                    background: 'rgba(255,255,255,0.05)',
                                    border: '1px solid rgba(255,255,255,0.1)',
                                    color: 'white',
                                    outline: 'none',
                                    appearance: 'none'
                                }}
                            >
                                {models.length === 0 ? (
                                    <option value={selectedModel}>Loading models...</option>
                                ) : (
                                    models.map((m, i) => (
                                        <option key={m.id || i} value={m.id} style={{ background: '#111' }}>
                                            {m.name || m.id}
                                        </option>
                                    ))
                                )}
                            </select>
                        </div>
                        {saving && <div style={{ fontSize: 12, color: 'var(--accent-primary)', marginTop: 8 }}>Saving configuration...</div>}
                    </div>
                </div>

                <div className="glass-panel">
                    <div className="clip-card-header" style={{ border: 'none', padding: 0, paddingBottom: 16 }}>
                        <span style={{ color: 'var(--accent-primary)', marginRight: '8px' }}>▶️</span>
                        Director Engine
                    </div>
                    <div style={{ fontSize: 18, fontWeight: 500, marginBottom: 16 }}>
                        Status: <span style={{ color: engineState.includes('Background') || engineState === 'Scanning...' || engineState === 'Starting...' ? 'var(--success)' : 'var(--text-primary)' }}>{engineState}</span>
                    </div>

                    <div style={{ marginBottom: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                        <label style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Target Scan Directories</label>
                        {watchFolders.map((folder, idx) => (
                            <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <input
                                    type="text"
                                    value={folder}
                                    placeholder="/Absolute/path/to/my/videos"
                                    onChange={(e) => updateWatchFolder(idx, e.target.value)}
                                    style={{
                                        flex: 1,
                                        padding: '10px 12px',
                                        borderRadius: '6px',
                                        background: 'rgba(255,255,255,0.05)',
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        color: 'white',
                                        outline: 'none'
                                    }}
                                />
                                <button
                                    onClick={() => startScan(folder)}
                                    disabled={engineState === 'Scanning...' || engineState === 'Scan Started in Background' || !folder.trim()}
                                    style={{ padding: '10px 16px', borderRadius: '6px', background: 'var(--accent-primary)', border: 'none', color: '#111', fontWeight: 600, cursor: (!folder.trim() || engineState === 'Scanning...' || engineState === 'Scan Started in Background') ? 'not-allowed' : 'pointer', opacity: (!folder.trim() || engineState === 'Scanning...' || engineState === 'Scan Started in Background') ? 0.5 : 1 }}>
                                    Scan
                                </button>
                                {watchFolders.length > 1 && (
                                    <button onClick={() => removeWatchFolder(idx)} style={{ padding: '10px', background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: '#fff', borderRadius: '6px', cursor: 'pointer' }}>×</button>
                                )}
                            </div>
                        ))}
                        <button onClick={addWatchFolder} style={{ marginTop: 4, padding: '8px', background: 'transparent', border: '1px dashed rgba(255,255,255,0.2)', color: 'var(--text-secondary)', borderRadius: '6px', cursor: 'pointer', fontSize: 12 }}>
                            + Add Another Folder
                        </button>
                    </div>

                    <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                        <label style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'block', marginBottom: 8 }}>Transcription (Local MLX Whisper — Apple Silicon)</label>
                        <button
                            className="btn-secondary"
                            onClick={startTranscribeAll}
                            disabled={isTranscribing}
                            style={{ width: '100%', padding: '10px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: 'white', cursor: isTranscribing ? 'not-allowed' : 'pointer', fontWeight: 500, opacity: isTranscribing ? 0.6 : 1 }}
                        >
                            {isTranscribing ? '⏳ Transcribing...' : '🎙️ Transcribe All Indexed Videos'}
                        </button>

                        {transcribeProgress && transcribeProgress.total > 0 && (
                            <div style={{ marginTop: 12 }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
                                    <span>
                                        {isTranscribing ? `🎙️ ${transcribeProgress.filename || 'Processing...'}` : (engineState === 'Transcription Complete' ? '✅ All done!' : `Paused at ${transcribeProgress.done}`)}
                                    </span>
                                    <span style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>{transcribeProgress.done} / {transcribeProgress.total} videos</span>
                                </div>
                                <div style={{ width: '100%', height: 4, borderRadius: 2, background: 'rgba(255,255,255,0.08)' }}>
                                    <div style={{ width: `${Math.round((transcribeProgress.done / transcribeProgress.total) * 100)}%`, height: '100%', borderRadius: 2, background: 'var(--accent-primary)', transition: 'width 0.4s ease' }} />
                                </div>
                            </div>
                        )}
                    </div>

                    {(engineState.includes('Background') || engineState.includes('Scanning')) && (
                        <div style={{ marginTop: 24, background: '#0a0a0a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, overflow: 'hidden' }}>
                            <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.05)', fontSize: 11, fontWeight: 600, color: '#888', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between' }}>
                                <span>TERMINAL ⏤ DIRECTOR_ENGINE.LOG</span>
                                <span style={{ color: 'var(--success)' }}>● LIVE</span>
                            </div>
                            <div style={{ padding: 12, fontFamily: 'monospace', fontSize: 11, color: '#10B981', lineHeight: 1.5, minHeight: 200, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                                {engineLogs.length === 0 ? (
                                    <div style={{ color: '#666' }}>Waiting for stdout stream...</div>
                                ) : (
                                    engineLogs.map((logStr, i) => (
                                        <div key={i} style={{ wordBreak: 'break-all', opacity: i === engineLogs.length - 1 ? 1 : Math.max(0.4, 1 - ((engineLogs.length - i) * 0.15)) }}>
                                            {logStr}
                                        </div>
                                    ))
                                )}
                            </div>
                        </div>
                    )}

                    {/* Archive-wide Duplicate Scanner */}
                    <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                        <label style={{ fontSize: 13, color: 'var(--text-secondary)', display: 'block', marginBottom: 8 }}>Archive Housekeeping</label>
                        <button
                            onClick={showDuplicates ? () => setShowDuplicates(false) : fetchDuplicates}
                            disabled={loadingDupes}
                            style={{ width: '100%', padding: '10px', borderRadius: '6px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', color: '#F87171', cursor: loadingDupes ? 'not-allowed' : 'pointer', fontWeight: 500, opacity: loadingDupes ? 0.6 : 1 }}
                        >
                            {loadingDupes ? '⏳ Scanning archive...' : showDuplicates ? `🔴 Hide Duplicates (${duplicateGroups.length} groups)` : '🔴 Find All Duplicate Files'}
                        </button>

                        {showDuplicates && !loadingDupes && (
                            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                                {duplicateGroups.length === 0 ? (
                                    <div style={{ padding: 16, textAlign: 'center', fontSize: 13, opacity: 0.5 }}>✅ No duplicates found in your archive.</div>
                                ) : (
                                    <>
                                        <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 4 }}>
                                            {duplicateGroups.reduce((s: number, g: any) => s + g.clips.length - 1, 0)} redundant files across {duplicateGroups.length} groups
                                        </div>
                                        {duplicateGroups.map((group: any) => (
                                            <div key={group.key} style={{ background: 'rgba(239,68,68,0.04)', border: '1px solid rgba(239,68,68,0.15)', borderRadius: 8, overflow: 'hidden' }}>
                                                <div style={{ padding: '8px 12px', background: 'rgba(239,68,68,0.08)', fontSize: 11, color: '#F87171', fontWeight: 600 }}>
                                                    📅 {group.clips[0].created} · {group.clips[0].duration}s · {group.clips.length} copies
                                                </div>
                                                {group.clips.map((clip: any, i: number) => (
                                                    <div key={clip.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderTop: i > 0 ? '1px solid rgba(255,255,255,0.04)' : 'none' }}>
                                                        <span style={{ flexShrink: 0, fontSize: 14 }}>{clip.suggested_keep ? '✅' : '🔴'}</span>
                                                        <div style={{ flex: 1, minWidth: 0 }}>
                                                            <div style={{ fontWeight: clip.suggested_keep ? 600 : 400, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{clip.filename}</div>
                                                            <div style={{ fontSize: 10, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1 }}>{clip.path}</div>
                                                        </div>
                                                        {!clip.suggested_keep && (
                                                            <button
                                                                onClick={() => deleteFromIndex(clip.id)}
                                                                title="Remove from index only — file on disk is untouched"
                                                                style={{ flexShrink: 0, padding: '3px 8px', borderRadius: 4, fontSize: 10, background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)', color: '#F87171', cursor: 'pointer' }}
                                                            >
                                                                Remove
                                                            </button>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        ))}
                                    </>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Danger Zone */}
                    <div style={{ marginTop: 32, paddingTop: 16, borderTop: '1px solid rgba(239, 68, 68, 0.2)' }}>
                        <label style={{ fontSize: 13, color: '#F87171', display: 'block', marginBottom: 8, fontWeight: 600 }}>Danger Zone</label>
                        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12 }}>
                            Resetting the database will wipe all indexed videos, transcriptions, and engine logs. Use this for testing or to start a fresh archive.
                        </p>
                        <button
                            onClick={handleDatabaseReset}
                            style={{
                                width: '100%',
                                padding: '10px',
                                borderRadius: '6px',
                                background: 'rgba(239,68,68,0.15)',
                                border: '1px solid rgba(239,68,68,0.3)',
                                color: '#F87171',
                                cursor: 'pointer',
                                fontWeight: 600,
                                fontSize: 13,
                                transition: 'all 0.2s'
                            }}
                            onMouseOver={(e) => e.currentTarget.style.background = 'rgba(239,68,68,0.25)'}
                            onMouseOut={(e) => e.currentTarget.style.background = 'rgba(239,68,68,0.15)'}
                        >
                            🗑️ Reset Video Database
                        </button>
                    </div>

                </div>
            </div>
        </div>
    );
}
