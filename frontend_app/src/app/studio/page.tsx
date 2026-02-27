'use client';
import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import Calendar from 'react-calendar';
import 'react-calendar/dist/Calendar.css';

// Opt 18: Reusable SSE stream reader hook — eliminates ~100 lines of duplicated buffer-management code.
function useSSEStream() {
    return useCallback(async (
        url: string,
        options: RequestInit,
        onChunk: (parsed: any) => void,
        onError?: () => void
    ) => {
        try {
            const res = await fetch(url, options);
            if (!res.body) throw new Error('No readable stream');
            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let done = false;
            let buffer = '';
            while (!done) {
                const { value, done: readerDone } = await reader.read();
                done = readerDone;
                if (value) {
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n\n');
                    buffer = lines.pop() || '';
                    for (const line of lines) {
                        for (const chunkStr of line.split('data: ').filter(Boolean)) {
                            try { onChunk(JSON.parse(chunkStr.trim())); } catch (e) { /* ignore */ }
                        }
                    }
                }
            }
        } catch (e) {
            onError && onError();
        }
    }, []);
}

function StoryPlanLoader({ content, totalClips }: { content: string, totalClips: number }) {
    const isDrafting = content.includes('Drafting story narrative');
    const [showDebug, setShowDebug] = useState(false);

    // Auto-scroll ref for the debug log container to prevent hijacking whole page scroll
    const logContainerRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (showDebug && logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [content, showDebug]);

    // Parse the stream content to find how many clips have been analyzed and which one is currently being processed
    const analyzeCount = (content.match(/Analyzing video/g) || []).length;

    // Extract the latest filename being processed for the holodeck animation
    const latestFileMatch = content.match(/Analyzing video ([^\s]+)/g);
    const activeFilename = latestFileMatch && latestFileMatch.length > 0
        ? latestFileMatch[latestFileMatch.length - 1].replace('Analyzing video ', '').replace('...', '')
        : null;

    return (
        <div style={{ padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                {/* Step 1: Video Analysis Node with Holodeck Animation */}
                <div style={{
                    width: 120, height: 120, borderRadius: 24,
                    background: isDrafting ? 'rgba(59, 130, 246, 0.1)' : 'rgba(59, 130, 246, 0.2)',
                    border: '2px solid',
                    borderColor: isDrafting ? 'rgba(59, 130, 246, 0.2)' : 'rgba(59, 130, 246, 0.8)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    boxShadow: isDrafting ? 'none' : '0 0 20px rgba(59, 130, 246, 0.3)',
                    transition: 'all 0.5s',
                    position: 'relative',
                    overflow: 'hidden'
                }}>
                    {/* Scanning animation bar inside the node */}
                    {!isDrafting && <div className="scanner-bar" />}

                    {/* Holodeck Thumbnail Injection */}
                    {!isDrafting && activeFilename && (
                        <img
                            key={activeFilename} // Forces re-render/re-animation when filename changes
                            src={`http://localhost:8000/api/thumbnail?path=${encodeURIComponent('/Volumes/X9 Pro/2011/09 (Sep)/' + activeFilename)}&t=2`}
                            alt="Processing..."
                            className="holodeck-thumb"
                            onError={(e) => { e.currentTarget.style.display = 'none'; }}
                        />
                    )}

                    <span style={{ fontSize: 40, zIndex: 20 }}>🎞️</span>
                    <span style={{ marginTop: 8, fontSize: 12, fontWeight: 'bold', color: '#60a5fa', zIndex: 20, textShadow: '0 2px 4px rgba(0,0,0,0.8)' }}>
                        {isDrafting ? 'Analysis Complete' : `${analyzeCount} / ${totalClips} Clips`}
                    </span>
                </div>

                {/* Connection line */}
                <div style={{ display: 'flex', gap: 8 }}>
                    <div className={`pulse-dot ${isDrafting ? 'active' : ''}`} style={{ animationDelay: '0s' }} />
                    <div className={`pulse-dot ${isDrafting ? 'active' : ''}`} style={{ animationDelay: '0.2s' }} />
                    <div className={`pulse-dot ${isDrafting ? 'active' : ''}`} style={{ animationDelay: '0.4s' }} />
                </div>

                {/* Step 2: Gemini Drafting Node */}
                <div style={{
                    width: 120, height: 120, borderRadius: '50%',
                    background: isDrafting ? 'rgba(16, 185, 129, 0.2)' : 'rgba(16, 185, 129, 0.05)',
                    border: '2px solid',
                    borderColor: isDrafting ? 'rgba(16, 185, 129, 0.8)' : 'rgba(16, 185, 129, 0.2)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    boxShadow: isDrafting ? '0 0 30px rgba(16, 185, 129, 0.4)' : 'none',
                    transition: 'all 0.5s'
                }}>
                    <span style={{ fontSize: 40, animation: isDrafting ? 'float 2s ease-in-out infinite' : 'none' }}>✨</span>
                    <span style={{ marginTop: 8, fontSize: 12, fontWeight: 'bold', color: '#34d399', textAlign: 'center', padding: '0 8px' }}>Gemini AI</span>
                </div>
            </div>

            <div style={{ textAlign: 'center' }}>
                <h3 style={{ margin: 0, color: '#fff', fontSize: 18 }}>
                    {isDrafting ? "Drafting Story Plan..." : "Analyzing Transcripts..."}
                </h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 8, maxWidth: 350 }}>
                    {isDrafting
                        ? "Gemini is arranging your clips into a cohesive narrative sequence based on transcriptions."
                        : "Extracting sentences and visual context from your selected footage..."}
                </p>
            </div>

            {/* Debug Toggle */}
            <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', marginTop: 16 }}>
                <button
                    onClick={() => setShowDebug(!showDebug)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
                >
                    <span>🐞</span> {showDebug ? 'Hide Stream Log' : 'View Stream Log'}
                </button>
                {showDebug && (
                    <div ref={logContainerRef} style={{ width: '100%', background: '#000', borderRadius: 8, padding: 16, marginTop: 12, fontSize: 12, fontFamily: 'monospace', color: '#60a5fa', maxHeight: 200, overflowY: 'auto', border: '1px solid rgba(255,255,255,0.1)', textAlign: 'left', whiteSpace: 'pre-wrap' }}>
                        {content}
                    </div>
                )}
            </div>
        </div>
    );
}

function VideoBuildLoader({ logs, status }: { logs: string[], status: string }) {
    const isComplete = status === 'Build Complete!';
    const [showDebug, setShowDebug] = useState(false);

    // Auto-scroll ref for the debug log container to prevent hijacking whole page scroll
    const logContainerRef = useRef<HTMLDivElement>(null);
    useEffect(() => {
        if (showDebug && logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [logs, showDebug]);

    return (
        <div style={{ padding: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 32 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
                {/* Step 1: Glueing scenes string */}
                <div style={{
                    width: 120, height: 120, borderRadius: '50%',
                    background: isComplete ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.1)',
                    border: '2px solid',
                    borderColor: isComplete ? 'rgba(16, 185, 129, 0.8)' : 'rgba(245, 158, 11, 0.8)',
                    display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                    boxShadow: isComplete ? 'none' : '0 0 30px rgba(245, 158, 11, 0.4)',
                    transition: 'all 0.5s',
                }}>
                    <span style={{ fontSize: 40, animation: isComplete ? 'none' : 'float 2s ease-in-out infinite' }}>🎞️</span>
                    <span style={{ marginTop: 8, fontSize: 12, fontWeight: 'bold', color: isComplete ? '#34d399' : '#fbbf24' }}>
                        {isComplete ? 'Glued!' : 'Glueing...'}
                    </span>
                </div>
            </div>

            <div style={{ textAlign: 'center' }}>
                <h3 style={{ margin: 0, color: '#fff', fontSize: 18 }}>
                    {isComplete ? "Video Complete!" : "Stitching Scenes Together..."}
                </h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: 14, marginTop: 8, maxWidth: 350 }}>
                    {isComplete
                        ? "Your video has been successfully compiled and is ready to watch."
                        : "FFmpeg is processing trims, normalizing audio, adjusting scaling, and writing the final container..."}
                </p>
            </div>

            {/* Debug Toggle */}
            <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end', marginTop: 16 }}>
                <button
                    onClick={() => setShowDebug(!showDebug)}
                    style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}
                >
                    <span>🐞</span> {showDebug ? 'Hide Terminal Output' : 'View Terminal Output'}
                </button>
                {showDebug && (
                    <div ref={logContainerRef} style={{ width: '100%', background: '#000', borderRadius: 8, padding: 16, marginTop: 12, fontSize: 12, fontFamily: 'monospace', color: '#10b981', maxHeight: 200, overflowY: 'auto', border: '1px solid rgba(16,185,129,0.2)', textAlign: 'left', whiteSpace: 'pre-wrap' }}>
                        {logs.map((log, idx) => (
                            <div key={idx} style={{ marginBottom: 4 }}>{log}</div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

// Opt 13: NLEViewer with memoised parsing — only re-runs when `content` changes, not on every SSE chunk.
function NLEViewer({ content, totalClips, onClipClick }: { content: string, totalClips: number, onClipClick?: (path: string, startTime: number) => void }) {
    const scenes = useMemo(() => {
        const lines = content.split('\n');
        const result: any[] = [];
        let currentScene: any = null;
        let currentMode: 'A' | 'B' | null = null;

        const extractPath = (imgSrc: string) => {
            if (!imgSrc) return '';
            try {
                const url = new URL(imgSrc);
                return url.searchParams.get('path') || '';
            } catch (e) {
                const match = imgSrc.match(/path=([^&]+)/);
                return match ? decodeURIComponent(match[1]) : '';
            }
        };

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            if (!line.trim()) continue;
            if (line.startsWith('## **SCENE')) {
                currentScene = { title: line.replace(/## \*\*SCENE \d+: (.*?)\*\*/, '$1'), blocks: [], broll: [] };
                result.push(currentScene);
            } else if (line.startsWith('*   **A-ROLL:**')) {
                currentMode = 'A';
            } else if (line.startsWith('*   **B-ROLL OVERLAYS:**')) {
                currentMode = 'B';
            } else if (currentMode === 'A' && line.startsWith('    *   Segment')) {
                const timeMatch = line.match(/\[([\d\.]+ - [\d\.]+)\]/);
                const textMatch = line.match(/\]\s+(.+?)\s*!\[thumbnail\]/);
                const rawText = textMatch ? textMatch[1].replace(/^\(|\)$/, '').trim() : '';
                const imgMatch = line.match(/!\[.*?\]\((.+)\)/);
                if (currentScene) {
                    const img = imgMatch ? imgMatch[1] : '';
                    currentScene.blocks.push({ time: timeMatch ? timeMatch[1] : '', text: rawText, img, path: extractPath(img) });
                }
            } else if (currentMode === 'B' && line.startsWith('    *   `')) {
                const fileMatch = line.match(/`(.*?)`/);
                const trimMatch = line.match(/Trim:\s*\[(.*?)\]/);
                const overlayMatch = line.match(/Overlay @\s*([\d\.:]+)/);
                const imgMatch = line.match(/!\[.*?\]\((.+)\)/);
                let rationale = '';
                if (i + 1 < lines.length && lines[i + 1].startsWith('        *   **RATIONALE:**')) {
                    rationale = lines[i + 1].replace('        *   **RATIONALE:**', '').trim();
                    i++;
                }
                if (currentScene) {
                    const img = imgMatch ? imgMatch[1] : '';
                    currentScene.broll.push({ file: fileMatch ? fileMatch[1].split('/').pop() : '', trim: trimMatch ? trimMatch[1] : '', overlay: overlayMatch ? overlayMatch[1] : '', img, rationale, path: extractPath(img) });
                }
            }
        }
        return result;
    }, [content]);

    return (
        <div className="nle-viewer">
            {scenes.map((scene: any, idx: number) => (
                <div key={idx} style={{ marginBottom: 40, background: '#111827', padding: 20, borderRadius: 12, border: '1px solid #1f2937' }}>
                    <h3 style={{ color: '#fff', marginTop: 0, marginBottom: 20, fontSize: 16 }}>SCENE {idx + 1}: {scene.title}</h3>
                    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 8 }}>
                        {/* V2 - B-Roll Track */}
                        <div className="track v2-track" style={{ display: 'flex', gap: 12, minHeight: 90, padding: 8, background: 'rgba(59, 130, 246, 0.05)', borderRadius: 8, border: '1px solid rgba(59, 130, 246, 0.1)' }}>
                            <div style={{ width: 60, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#60a5fa', fontWeight: 'bold', fontSize: 12, borderRight: '1px solid rgba(59, 130, 246, 0.2)' }}>V2</div>
                            <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 4 }}>
                                {scene.broll.map((b: any, bIdx: number) => {
                                    const bStart = b.trim ? parseFloat(b.trim.split('-')[0].replace(':', '.')) : 0;
                                    return (
                                        <div
                                            key={bIdx}
                                            onClick={() => b.path && onClipClick && onClipClick(b.path, bStart)}
                                            style={{ display: 'flex', gap: 8, background: 'rgba(59, 130, 246, 0.15)', border: '1px solid rgba(59, 130, 246, 0.4)', borderRadius: 6, padding: 6, width: 220, flexShrink: 0, cursor: b.path ? 'pointer' : 'default', transition: 'all 0.2s' }}
                                            onMouseEnter={(e) => b.path && (e.currentTarget.style.transform = 'translateY(-2px)')}
                                            onMouseLeave={(e) => b.path && (e.currentTarget.style.transform = 'translateY(0)')}
                                        >
                                            {b.img && <img src={b.img} style={{ width: 68, height: 46, objectFit: 'cover', borderRadius: 4 }} alt="B-Roll Thumbnail" />}
                                            <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', justifyContent: 'center' }}>
                                                <span style={{ fontSize: 12, fontWeight: 'bold', color: '#93c5fd', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.file}</span>
                                                <span style={{ fontSize: 11, color: '#bfdbfe', marginTop: 2 }}>
                                                    @ {b.overlay}s {b.trim && `| Trim: [${b.trim}]`}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                                {scene.broll.length === 0 && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.2)', paddingLeft: 8, display: 'flex', alignItems: 'center' }}>No overlays</div>}
                            </div>
                        </div>

                        {/* V1 - A-Roll Track */}
                        <div className="track v1-track" style={{ display: 'flex', gap: 12, minHeight: 120, padding: 8, background: 'rgba(16, 185, 129, 0.05)', borderRadius: 8, border: '1px solid rgba(16, 185, 129, 0.1)' }}>
                            <div style={{ width: 60, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#10b981', fontWeight: 'bold', fontSize: 12, borderRight: '1px solid rgba(16, 185, 129, 0.2)' }}>V1</div>
                            <div style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 4 }}>
                                {scene.blocks.map((b: any, bIdx: number) => {
                                    const tStart = b.time ? parseFloat(b.time.split(' - ')[0]) : 0;
                                    return (
                                        <div
                                            key={bIdx}
                                            onClick={() => b.path && onClipClick && onClipClick(b.path, tStart)}
                                            style={{ display: 'flex', flexDirection: 'column', gap: 6, background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: 6, padding: 6, width: 220, flexShrink: 0, cursor: b.path ? 'pointer' : 'default', transition: 'all 0.2s' }}
                                            onMouseEnter={(e) => b.path && (e.currentTarget.style.transform = 'translateY(-2px)')}
                                            onMouseLeave={(e) => b.path && (e.currentTarget.style.transform = 'translateY(0)')}
                                        >
                                            <div style={{ position: 'relative', width: '100%', aspectRatio: '16/9', background: '#000', borderRadius: 4, overflow: 'hidden' }}>
                                                {b.img && <img src={b.img} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="A-Roll Thumbnail" />}
                                                <div style={{ position: 'absolute', bottom: 4, right: 4, background: 'rgba(0,0,0,0.7)', padding: '2px 4px', borderRadius: 4, fontSize: 10, fontFamily: 'monospace', color: '#fff' }}>{b.time}</div>
                                            </div>
                                            <div style={{ fontSize: 11, color: '#a7f3d0', lineHeight: 1.3, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                                "{b.text}"
                                            </div>
                                        </div>
                                    );
                                })}
                                {scene.blocks.length === 0 && <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.2)', paddingLeft: 8, display: 'flex', alignItems: 'center' }}>Processing A-Roll...</div>}
                            </div>
                        </div>
                    </div>
                </div>
            ))}
            {content && !content.includes('## **SCENE') && (
                <StoryPlanLoader content={content} totalClips={totalClips} />
            )}
        </div>
    );
}

// Opt 12: Lazy clip preview — shows static thumbnail, swaps to <video> on click.
function ClipPreview({ path, thumbSrc }: { path: string, thumbSrc: string }) {
    const isSupported = path.toLowerCase().match(/\.(mp4|mov|m4v|webm)$/);
    const [playing, setPlaying] = useState(false);
    if (playing) {
        if (!isSupported) {
            return (
                <div style={{ width: '100%', aspectRatio: '16/9', backgroundColor: '#000', borderRadius: 6, overflow: 'hidden', marginBottom: 12, position: 'relative' }}>
                    <img src={thumbSrc} style={{ width: '100%', height: '100%', objectFit: 'contain' }} alt="Unsupported format" />
                    <div style={{ position: 'absolute', top: 8, left: 8, background: 'rgba(239, 68, 68, 0.9)', color: 'white', padding: '4px 8px', borderRadius: 4, fontSize: 11, fontWeight: 'bold' }}>Format Unsupported in Browser</div>
                </div>
            );
        }
        return (
            <div style={{ width: '100%', aspectRatio: '16/9', backgroundColor: '#000', borderRadius: 6, overflow: 'hidden', marginBottom: 12 }}>
                <video
                    src={`http://localhost:8000/api/video?path=${encodeURIComponent(path)}#t=0.1`}
                    controls
                    autoPlay
                    style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                />
            </div>
        );
    }
    return (
        <div
            onClick={() => setPlaying(true)}
            style={{ width: '100%', aspectRatio: '16/9', backgroundColor: '#000', borderRadius: 6, overflow: 'hidden', marginBottom: 12, cursor: 'pointer', position: 'relative' }}
        >
            <img src={thumbSrc} style={{ width: '100%', height: '100%', objectFit: 'cover' }} alt="Clip thumbnail" />
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(0,0,0,0.3)' }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', background: 'rgba(255,255,255,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18 }}>▶</div>
            </div>
        </div>
    );
}

export default function Studio() {
    const [query, setQuery] = useState('');
    const [clips, setClips] = useState<any[]>([]);
    const [currentPage, setCurrentPage] = useState(1);
    const PAGE_SIZE = 50;
    const [insights, setInsights] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [plan, setPlan] = useState<{ path: string, content: string } | null>(null);
    const [planError, setPlanError] = useState<string | null>(null);
    const [buildStatus, setBuildStatus] = useState('');
    const [date, setDate] = useState<any>(new Date());
    const [activeVideo, setActiveVideo] = useState<{ path: string, startTime: number } | null>(null);
    const [buildLogs, setBuildLogs] = useState<string[]>([]);
    const [finalVideoPath, setFinalVideoPath] = useState('');

    // Transcription Upgrade State
    const [isUpgrading, setIsUpgrading] = useState(false);
    const [upgradeLogs, setUpgradeLogs] = useState<string[]>([]);

    // Duplicate Detection State (client-side filter on current results)
    const [hideDuplicates, setHideDuplicates] = useState(true);

    // Clip Selection State — tracks which clips are included in the story plan
    const [selectedClipIds, setSelectedClipIds] = useState<Set<number>>(new Set());

    // Opt 18: Shared SSE hook — replaces 4 duplicated read loops.
    const sseStream = useSSEStream();

    // Opt 14: Memoize paginated clips slice — only recomputes when clips/page/hideDuplicates changes.
    const dedupedClips = useMemo(() => {
        if (!hideDuplicates) return clips;
        // Keep only the first clip per (created, rounded duration) group.
        // Same timestamp + same length = same clip regardless of filename.
        const seen = new Set<string>();
        return clips.filter((c: any) => {
            const key = `${c.created}|${Math.round(parseFloat(c.duration) || 0)}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }, [clips, hideDuplicates]);

    const paginatedClips = useMemo(
        () => dedupedClips.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE),
        [dedupedClips, currentPage]
    );

    // Opt 15: Pre-compute calendar timeline into a Map for O(1) tile lookups.
    const timelineMap = useMemo(() => {
        const map = new Map<string, any>();
        if (insights?.timeline) {
            for (const entry of insights.timeline) map.set(entry.date, entry);
        }
        return map;
    }, [insights]);

    useEffect(() => {
        fetch('http://localhost:8000/api/insights')
            .then(res => res.json())
            .then(data => setInsights(data))
            .catch(err => console.error('Failed to fetch insights', err));
    }, []);

    const performSearch = async (searchQuery: string) => {
        setLoading(true);
        try {
            const isDate = /^\d{4}-\d{2}-\d{2}$/.test(searchQuery);
            const res = await fetch('http://localhost:8000/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(isDate ? { date: searchQuery } : { query: searchQuery })
            });
            const data = await res.json();
            setClips(data.clips || []);
            setCurrentPage(1);
            setPlan(null);
            setBuildStatus('');
            setBuildLogs([]);
            setFinalVideoPath('');
            // Default: all deduped clips selected
            setSelectedClipIds(new Set((data.clips || []).map((c: any) => c.id)));
        } catch (e) {
            alert('Error searching clips');
        }
        setLoading(false);
    };

    const searchClips = () => performSearch(query);

    const handleTagClick = (tag: string) => {
        setQuery(tag);
        performSearch(tag);
    };

    const handleDateClick = (clickedDate: Date) => {
        setDate(clickedDate);
        const offset = clickedDate.getTimezoneOffset();
        const localDate = new Date(clickedDate.getTime() - (offset * 60 * 1000));
        const dateStr = localDate.toISOString().split('T')[0];
        setQuery(dateStr);
        performSearch(dateStr);
    };

    const generatePlan = async () => {
        setLoading(true);
        setFinalVideoPath('');
        setBuildStatus('');
        setBuildLogs([]);
        setPlanError(null);
        setPlan({ path: '', content: '' });
        const clipsForPlan = clips.filter((c: any) => selectedClipIds.has(c.id));
        await sseStream(
            'http://localhost:8000/api/plan/stream',
            { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: query || 'Generated_Vlog', clips: clipsForPlan }) },
            (parsed) => {
                if (parsed.error) {
                    // Backend surfaced a fatal error event
                    setPlanError(parsed.error);
                } else if (parsed.chunk && parsed.chunk.startsWith('DONE:')) {
                    const finalPath = parsed.chunk.replace('DONE:', '');
                    setPlan(prev => prev ? { ...prev, path: finalPath } : { path: finalPath, content: '' });
                } else if (parsed.chunk) {
                    setPlan(prev => prev ? { ...prev, content: prev.content + parsed.chunk } : { path: '', content: parsed.chunk });
                }
            },
            () => setPlanError('Connection lost mid-stream. Please try regenerating.')
        );
        setLoading(false);
    };

    const upgradeClips = async () => {
        setIsUpgrading(true);
        setUpgradeLogs([]);
        await sseStream(
            'http://localhost:8000/api/transcription/upgrade',
            { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: query || 'Upgrade', clips }) },
            (parsed) => {
                if (parsed.chunk?.startsWith('DONE')) { setUpgradeLogs(prev => [...prev, 'Upgrade Complete!']); searchClips(); }
                else if (parsed.chunk) setUpgradeLogs(prev => [...prev, parsed.chunk.trim()]);
            },
            () => alert('Error upgrading transcription')
        );
        setIsUpgrading(false);
    };

    const upgradeSingleClip = async (clip: any) => {
        setIsUpgrading(true);
        setUpgradeLogs([]);
        await sseStream(
            'http://localhost:8000/api/transcription/upgrade',
            { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: `Upgrade_${clip.filename}`, clips: [clip] }) },
            (parsed) => {
                if (parsed.chunk?.startsWith('DONE')) { setUpgradeLogs(prev => [...prev, 'Upgrade Complete!']); searchClips(); }
                else if (parsed.chunk) setUpgradeLogs(prev => [...prev, parsed.chunk.trim()]);
            },
            () => alert('Error upgrading transcription')
        );
        setIsUpgrading(false);
    };

    const buildVlog = async () => {
        if (!plan) return;
        setBuildStatus('Triggering FFmpeg build...');
        setBuildLogs([]);
        setFinalVideoPath('');
        await sseStream(
            'http://localhost:8000/api/build',
            { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ plan_path: plan.path }) },
            (parsed) => {
                if (parsed.done) {
                    setBuildStatus('Build Complete!');
                    setFinalVideoPath(parsed.done);
                } else if (parsed.error) {
                    // FFmpeg exited with a non-zero code — re-enable the button
                    setBuildStatus('');
                    setBuildLogs(prev => [...prev, `❌ Build failed: ${parsed.error}`]);
                } else if (parsed.status) {
                    setBuildLogs(prev => [...prev, parsed.status]);
                }
            },
            // Connection-level error — also re-enable the button
            () => { setBuildStatus(''); setBuildLogs(prev => [...prev, '❌ Lost connection to build server.']); }
        );
    };

    return (
        <div>
            {/* Hero Header unified panel */}
            <div className="glass-panel" style={{
                marginBottom: 32,
                padding: '24px 32px',
                background: 'linear-gradient(145deg, rgba(31, 41, 55, 0.4) 0%, rgba(17, 24, 39, 0.8) 100%)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                display: 'flex',
                gap: 32,
                alignItems: 'center'
            }}>

                {/* Left side: branding & search */}
                <div style={{ flex: '1 1 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
                    <div>
                        <h1 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '28px', margin: '0 0 8px 0' }}>
                            <span>✨</span> AI Studio
                        </h1>
                        <p className="subtitle" style={{ margin: 0, fontSize: '15px' }}>
                            Search your archive to generate rough cuts automatically.
                        </p>
                    </div>

                    <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
                        <div style={{ position: 'relative', flexGrow: 1, maxWidth: 640 }}>
                            <span style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', opacity: 0.5 }}>🔍</span>
                            <input
                                type="text"
                                placeholder="Search by keyword, theme, or date (YYYY-MM-DD)..."
                                value={query}
                                onChange={e => setQuery(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && searchClips()}
                                style={{
                                    width: '100%',
                                    paddingLeft: 44,
                                    height: 48,
                                    fontSize: 16,
                                    backgroundColor: 'rgba(0,0,0,0.2)',
                                    border: '1px solid rgba(255,255,255,0.1)'
                                }}
                            />
                        </div>
                        <button className="btn-primary" onClick={searchClips} disabled={loading} style={{ height: 48, padding: '0 24px' }}>
                            Search
                        </button>
                    </div>

                    {/* Insights snippet */}
                    {insights && (
                        <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: '13px', color: 'var(--text-secondary)' }}>
                            <div style={{ background: 'rgba(59, 130, 246, 0.1)', padding: '6px 12px', borderRadius: 20 }}>
                                <b>{insights.total_clips}</b> clips total
                            </div>
                            <div style={{ background: 'rgba(16, 185, 129, 0.1)', padding: '6px 12px', borderRadius: 20 }}>
                                <b>{insights.transcribed_clips}</b> transcribed
                            </div>
                        </div>
                    )}
                </div>

                {/* Right side: Calendar embedded cleanly */}
                <div style={{
                    width: 380,
                    minHeight: 330,
                    background: 'rgba(0, 0, 0, 0.15)',
                    borderRadius: 16,
                    padding: 24,
                    border: '1px solid rgba(255, 255, 255, 0.03)',
                    boxShadow: 'inset 0 2px 10px rgba(0,0,0,0.2)'
                }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 12, textAlign: 'center', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                        Timeline
                    </div>
                    {insights ? (
                        <Calendar
                            onChange={(val) => handleDateClick(val as Date)}
                            value={date}
                            className="custom-calendar minimalist-calendar"
                            tileClassName={({ date: tileDate, view }) => {
                                if (view === 'month') {
                                    const offset = tileDate.getTimezoneOffset();
                                    const localDate = new Date(tileDate.getTime() - (offset * 60 * 1000));
                                    const dateStr = localDate.toISOString().split('T')[0];
                                    return timelineMap.has(dateStr) ? 'has-video' : null;
                                }
                                return null;
                            }}
                            tileContent={({ date: tileDate, view }) => {
                                if (view === 'month') {
                                    const offset = tileDate.getTimezoneOffset();
                                    const localDate = new Date(tileDate.getTime() - (offset * 60 * 1000));
                                    const dateStr = localDate.toISOString().split('T')[0];
                                    const found = timelineMap.get(dateStr);
                                    if (found) {
                                        return <div title={`${found.count} clips recorded`} style={{ position: 'absolute', bottom: '2px', left: '50%', transform: 'translateX(-50%)', width: '4px', height: '4px', backgroundColor: 'var(--accent-primary)', borderRadius: '50%' }} />;
                                    }
                                }
                                return null;
                            }}
                        />
                    ) : (
                        <div style={{ width: 250, height: 250, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}>Loading...</div>
                    )}
                </div>
            </div>





            {clips.length > 0 && !plan && (
                <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                            <h2 style={{ margin: 0 }}>Found {clips.length} Clips</h2>
                            <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                {selectedClipIds.size} selected
                            </span>
                            <button
                                onClick={() => setSelectedClipIds(new Set(dedupedClips.map((c: any) => c.id)))}
                                style={{ background: 'transparent', border: 'none', color: 'var(--accent-primary)', fontSize: 12, cursor: 'pointer', padding: 0 }}
                            >All</button>
                            <button
                                onClick={() => setSelectedClipIds(new Set())}
                                style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: 12, cursor: 'pointer', padding: 0 }}
                            >None</button>
                        </div>
                        <div style={{ display: 'flex', gap: 12 }}>
                            <button className="btn-secondary" onClick={upgradeClips} disabled={loading || isUpgrading} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span>🎙️</span> Upgrade All Transcription
                            </button>
                            <button className="btn-primary" onClick={generatePlan} disabled={loading || isUpgrading || selectedClipIds.size === 0} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span>🎬</span> Generate Story Plan {selectedClipIds.size > 0 && selectedClipIds.size < dedupedClips.length ? `(${selectedClipIds.size} clips)` : ''}
                            </button>
                        </div>
                    </div>

                    {upgradeLogs.length > 0 && (
                        <div style={{ background: '#000', borderRadius: 8, padding: 16, fontFamily: 'monospace', fontSize: 12, color: '#60a5fa', maxHeight: 200, overflowY: 'auto', marginBottom: 24, border: '1px solid rgba(96,165,250,0.2)' }}>
                            <div style={{ fontWeight: 'bold', marginBottom: 8, color: '#fff' }}>Transcription Upgrade Progress:</div>
                            {upgradeLogs.map((log: string, idx: number) => (
                                <div key={idx} style={{ marginBottom: 4 }}>{log}</div>
                            ))}
                        </div>
                    )}

                    <div className="grid">
                        {/* Opt 12 + 14: Only render the current page of clips, each as a thumbnail (not a video). */}
                        {paginatedClips.map((c: any) => {
                            const wordCount = c.transcription ? c.transcription.split(/\s+/).length : 0;
                            const isBRollTag = c.visual_tags?.toLowerCase().includes('b-roll');
                            const role = (isBRollTag || wordCount <= 12) ? 'b-roll' : 'a-roll';
                            const displayTags = c.visual_tags?.split(',').map((t: string) => t.trim()).filter((t: string) => t.toLowerCase() !== 'b-roll').slice(0, 3) || [];
                            const thumbSrc = `http://localhost:8000/api/thumbnail?path=${encodeURIComponent(c.path)}&t=2`;

                            return (
                                <div
                                    key={c.id}
                                    className={`clip-card ${role}`}
                                    style={{ display: 'flex', flexDirection: 'column', opacity: selectedClipIds.has(c.id) ? 1 : 0.45, transition: 'opacity 0.2s' }}
                                >
                                    <div className="clip-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--accent-primary)', marginBottom: 12, gap: 8 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                                            <input
                                                type="checkbox"
                                                checked={selectedClipIds.has(c.id)}
                                                onChange={() => setSelectedClipIds(prev => {
                                                    const next = new Set(prev);
                                                    next.has(c.id) ? next.delete(c.id) : next.add(c.id);
                                                    return next;
                                                })}
                                                style={{ flexShrink: 0, width: 15, height: 15, cursor: 'pointer', accentColor: 'var(--accent-primary)' }}
                                            />
                                            <span style={{ flexShrink: 0 }}>▶️</span>
                                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.filename}</span>
                                        </div>
                                        <button
                                            onClick={() => upgradeSingleClip(c)}
                                            disabled={loading || isUpgrading}
                                            title="Upgrade Transcription for this video"
                                            style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '1.2rem', opacity: (loading || isUpgrading) ? 0.5 : 1, padding: 0, flexShrink: 0 }}
                                        >
                                            🎙️
                                        </button>
                                    </div>
                                    {/* Opt 12: Render thumbnail first, swap to video on click. */}
                                    <ClipPreview path={c.path} thumbSrc={thumbSrc} />
                                    <div className="clip-card-body" style={{ flex: 1 }}>
                                        <p><strong>Duration:</strong> {c.duration}s</p>
                                        {c.transcription && <p style={{ fontStyle: 'italic', opacity: 0.8, marginTop: 8 }}>"{c.transcription.substring(0, 80)}..."</p>}
                                        <div style={{ marginTop: 12 }}>
                                            <span className={`tag ${role}-tag`} style={{ fontWeight: 600, letterSpacing: '0.5px' }}>{role.toUpperCase()}</span>
                                            {displayTags.map((t: string, i: number) => (
                                                <span key={i} className="tag">{t}</span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                    {clips.length > PAGE_SIZE && (
                        <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '32px', alignItems: 'center' }}>
                            <button
                                className="btn-secondary"
                                disabled={currentPage === 1}
                                onClick={() => setCurrentPage((p: number) => Math.max(1, p - 1))}
                            >
                                Previous
                            </button>
                            <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
                                Page {currentPage} of {Math.ceil(clips.length / PAGE_SIZE)}
                            </span>
                            <button
                                className="btn-secondary"
                                disabled={currentPage === Math.ceil(clips.length / PAGE_SIZE)}
                                onClick={() => setCurrentPage((p: number) => Math.min(Math.ceil(clips.length / PAGE_SIZE), p + 1))}
                            >
                                Next
                            </button>
                        </div>
                    )}
                </>
            )}

            {planError && (
                <div style={{ margin: '16px 0', padding: '16px 20px', background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.35)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16 }}>
                    <div>
                        <div style={{ fontWeight: 600, color: '#F87171', marginBottom: 4 }}>⚠️ Story Plan Error</div>
                        <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.6)' }}>{planError}</div>
                    </div>
                    <button
                        onClick={generatePlan}
                        disabled={loading}
                        style={{ flexShrink: 0, padding: '8px 18px', borderRadius: 8, background: 'rgba(239,68,68,0.2)', border: '1px solid rgba(239,68,68,0.4)', color: '#F87171', fontWeight: 600, fontSize: 13, cursor: loading ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap' }}
                    >
                        🔄 Regenerate
                    </button>
                </div>
            )}

            {plan && (
                <div className="glass-panel">
                    {/* The Generating Story Plan logic currently runs here. We want to hide the "Build Video" buttons completely if the plan isn't fully generated (i.e. plan.path is empty and we are still rendering the StoryPlanLoader) */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: plan.path ? 24 : 0 }}>
                        <div>
                            <h2 style={{ margin: 0, color: plan.path ? 'var(--success)' : '#60a5fa' }}>
                                {plan.path ? "Story Plan Generated!" : "Generating Story Plan..."}
                            </h2>
                            {plan.path && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 4 }}>Saved to: {plan.path}</div>}
                        </div>
                        {plan.path && (
                            <button
                                className="btn-primary"
                                onClick={buildVlog}
                                disabled={!!buildStatus && buildStatus !== 'Build Complete!'}
                                style={{
                                    background: (!!buildStatus && buildStatus !== 'Build Complete!') ? 'rgba(255,255,255,0.1)' : 'var(--success)',
                                    color: (!!buildStatus && buildStatus !== 'Build Complete!') ? 'rgba(255,255,255,0.3)' : '#fff',
                                    cursor: (!!buildStatus && buildStatus !== 'Build Complete!') ? 'not-allowed' : 'pointer',
                                    display: 'flex', alignItems: 'center', gap: 8
                                }}
                            >
                                <span>🎞️</span> Build my video
                            </button>
                        )}
                    </div>

                    {buildStatus && (
                        <div style={{ padding: 16, background: 'rgba(16, 185, 129, 0.1)', color: 'var(--success)', borderRadius: 8, marginBottom: 24, fontWeight: 500 }}>
                            {buildStatus}
                        </div>
                    )}

                    {buildLogs.length > 0 && (
                        <VideoBuildLoader logs={buildLogs} status={buildStatus} />
                    )}

                    {finalVideoPath && (
                        <div style={{ marginBottom: 24, borderRadius: 12, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
                            <div style={{ padding: 12, background: 'rgba(0,0,0,0.5)', fontSize: 13, color: '#aaa', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                Final Output: {finalVideoPath.split('/').pop()}
                            </div>
                            <video
                                controls
                                autoPlay
                                style={{ width: '100%', display: 'block' }}
                                src={`http://localhost:8000/api/video?path=${encodeURIComponent(finalVideoPath)}&t=${Date.now()}`}
                            />
                        </div>
                    )}
                    <NLEViewer
                        content={plan.content}
                        totalClips={clips.length}
                        onClipClick={(path, startTime) => setActiveVideo({ path, startTime })}
                    />
                </div>
            )}

            {/* Video Modal Popup */}
            {activeVideo && (
                <div
                    style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.85)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40 }}
                    onClick={() => setActiveVideo(null)}
                >
                    <div style={{ position: 'relative', width: '100%', maxWidth: 1000, background: '#000', borderRadius: 12, overflow: 'hidden', boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)' }} onClick={e => e.stopPropagation()}>
                        {activeVideo.path.toLowerCase().match(/\.(mp4|mov|m4v|webm)$/) ? (
                            <video
                                controls
                                autoPlay
                                style={{ width: '100%', display: 'block' }}
                                src={`http://localhost:8000/api/video?path=${encodeURIComponent(activeVideo.path)}`}
                                onLoadedMetadata={(e) => {
                                    if (activeVideo.startTime > 0) {
                                        e.currentTarget.currentTime = activeVideo.startTime;
                                    }
                                }}
                            />
                        ) : (
                            <div style={{ width: '100%', aspectRatio: '16/9', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                <img src={`http://localhost:8000/api/thumbnail?path=${encodeURIComponent(activeVideo.path)}`} style={{ width: '100%', height: '100%', objectFit: 'contain' }} alt="Unsupported fallback" />
                                <div style={{ position: 'absolute', top: 24, left: 24, background: 'rgba(239, 68, 68, 0.9)', color: 'white', padding: '6px 12px', borderRadius: 6, fontSize: 13, fontWeight: 'bold' }}>Format Unsupported in Browser</div>
                            </div>
                        )}
                        <button
                            onClick={() => setActiveVideo(null)}
                            style={{ position: 'absolute', top: 16, right: 16, width: 36, height: 36, borderRadius: '50%', background: 'rgba(0,0,0,0.5)', color: 'white', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, zIndex: 10 }}
                        >
                            ✕
                        </button>
                        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '12px 16px', background: 'linear-gradient(transparent, rgba(0,0,0,0.8))', color: '#aaa', fontSize: 12, pointerEvents: 'none' }}>
                            {activeVideo.path.split('/').pop()} @ {activeVideo.startTime}s
                        </div>
                    </div>
                </div>
            )}

            <style jsx global>{`
                .interactive-tag:hover {
                    background-color: rgba(99, 102, 241, 0.2) !important;
                    transform: scale(1.05);
                }
                .custom-calendar {
                    background: transparent !important;
                    border: none !important;
                    font-family: 'Inter', sans-serif !important;
                    color: var(--text-primary) !important;
                    width: 100% !important;
                }
                .react-calendar__tile {
                    color: var(--text-primary) !important;
                    border-radius: 8px;
                    transition: var(--transition);
                    position: relative;
                }
                .react-calendar__tile:enabled:hover, .react-calendar__tile:enabled:focus {
                    background-color: var(--panel-bg-hover) !important;
                }
                .react-calendar__tile--now {
                    background: rgba(99, 102, 241, 0.1) !important;
                    color: var(--accent-primary) !important;
                    font-weight: bold;
                }
                .react-calendar__tile--active {
                    background: var(--accent-primary) !important;
                    color: white !important;
                    box-shadow: 0 4px 14px 0 var(--accent-glow);
                }
                .react-calendar__navigation button {
                    color: var(--text-primary) !important;
                    min-width: 44px;
                    background: none;
                    font-size: 16px;
                    margin-top: 8px;
                }
                .react-calendar__navigation button:enabled:hover, .react-calendar__navigation button:enabled:focus {
                    background-color: var(--panel-bg-hover) !important;
                }
                .react-calendar__month-view__weekdays {
                    color: var(--text-secondary) !important;
                    font-weight: 600;
                    text-transform: uppercase;
                    font-size: 11px;
                }
                .react-calendar__month-view__days__day--neighboringMonth {
                    color: rgba(255, 255, 255, 0.1) !important;
                }
                abbr[title] {
                    text-decoration: none !important;
                }
                .has-video {
                    background: rgba(255, 255, 255, 0.05) !important;
                }
                .has-video:hover {
                    background: rgba(99, 102, 241, 0.2) !important;
                }
            `}</style>
        </div>
    );
}
