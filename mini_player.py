# -*- coding: utf-8 -*-
# Mini Player
# IT('s) Possible 
# 2026.11.01
"""
MovieScout Erweiterung: Lokale Direktwiedergabe
Team IT('s) Possible

Direkte Dateiauswahl, Fit/Fill im perfekten bläulichen MovieScout-Design.
"""

import os

EXT_ID = 'mini_player.py'
EXT_NAME = 'Mini Player'
EXT_DESCRIPTION = 'Direkte Medienwiedergabe im bläulichen MovieScout-Design.'
EXT_LINKS = [('Lokale Medien öffnen', 'index')]
EXT_SETTINGS = []

_api = None

def register(api):
    global _api
    _api = api

    def seite(req):
        return r'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>MovieScout - Lokale Medien</title>
<style>
:root {
    --bg: #10131a;
    --panel: #1a1f2c;
    --panel2: #222a3b;
    --border: #30394e;
    --text: #f1f3f8;
    --muted: #9da6b7;
    --accent: #3b82f6;      /* Angepasst an --blue-success */
    --accent-hover: #2563eb; /* Angepasst an Success-Hover */
    --blue-success: #3b82f6; /* Einheitliches Blau für Aktionen */
}
* { box-sizing: border-box; }
body {
    margin: 0; padding: 16px;
    background: var(--bg); color: var(--text);
    font-family: system-ui, -apple-system, sans-serif;
}
.container { max-width: 900px; margin: auto; }
.header { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.header h1 { font-size: 22px; margin: 0; font-weight: 700; color: var(--text); }
.subtitle { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.card {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 16px; padding: 18px; margin-bottom: 16px;
}
.card h2 { font-size: 16px; margin: 0 0 14px; font-weight: 600; color: var(--text); }
button {
    border: 0; border-radius: 10px; padding: 13px 16px;
    color: white; background: var(--blue-success); font-size: 14px;
    font-weight: 600; cursor: pointer; width: 100%;
    border: 1px solid var(--border);
    transition: background 0.2s, transform 0.1s;
}
button:active { transform: scale(0.98); }
.primary { background: var(--blue-success); border-color: transparent; }
.primary:hover { background: #2563eb; }
.success { background: var(--blue-success); border-color: transparent; }
.success:hover { background: #2563eb; }
.filter { padding: 10px 14px; font-size: 13px; background: var(--panel2); }
.filter.active { background: var(--blue-success); border-color: transparent; }
input[type="file"] { display: none; }
.player {
    background: #000; border-radius: 12px; overflow: hidden;
    position: relative; display: flex; align-items: center; justify-content: center;
    border: 1px solid var(--border);
}
.player video, .player audio, .player img {
    display: block; width: 100%; max-height: 55vh; object-fit: contain; background: #000;
}
.player audio { padding: 20px; }
.player-controls { display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; }
.player-controls button { flex: 1; min-width: 80px; padding: 11px; font-size: 13px; background: var(--blue-success); border-color: transparent; }
.player-controls button:hover { background: #2563eb; }
.file-name { font-weight: 600; font-size: 14px; color: var(--text); word-break: break-all; margin-top: 12px; }
.hidden { display: none !important; }
.status { color: var(--blue-success); font-size: 12px; margin-top: 10px; font-weight: 500; }
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <span style="font-size:28px">📂</span>
        <h1>Lokale Medien (Direkt)</h1>
    </div>
    <div class="subtitle">Wähle Datei im Dateimanager aus und spiele sie direkt ab.</div>

    <div class="card">
        <h2>📁 Media Datei auswählen...</h2>
        <button class="primary" onclick="document.getElementById('picker').click()">Dateimanager öffnen</button>
        <input type="file" id="picker" multiple accept="video/*,audio/*,image/*" onchange="handleFileSelect(this.files)">
        <div class="status" id="status">Bereit.</div>
    </div>

    <div class="card hidden" id="playerCard">
        <h2>▶ Player</h2>
        <div class="player" id="player"></div>
        <div class="file-name" id="playerInfo">-</div>
        
        <div class="player-controls">
            <button onclick="prevFile()">⏮ Zurück</button>
            <button class="success" onclick="togglePlay()" id="playBtn">⏸ Pause</button>
            <button onclick="nextFile()">Weiter ⏭</button>
        </div>

        <div class="player-controls" id="videoControls" style="display:none;">
            <button onclick="setFitMode('contain')" id="btnContain" class="filter active">Fit</button>
            <button onclick="setFitMode('cover')" id="btnCover" class="filter">Fill</button>
        </div>

        <div class="player-controls">
            <button onclick="toggleFullscreen()">⛶ Vollbild</button>
            <button onclick="stopPlayer()" class="primary">⏹ Schließen / Stop</button>
        </div>
    </div>
</div>

<script>
let currentFiles = [];
let currentIndex = -1;
let currentBlobUrl = null;
let currentEl = null;
let currentFit = 'contain';

function handleFileSelect(files) {
    if (!files || !files.length) return;
    
    currentFiles = Array.from(files);
    currentIndex = 0;
    playCurrentFile();
    
    document.getElementById('picker').value = '';
}

function playCurrentFile() {
    if (currentIndex < 0 || currentIndex >= currentFiles.length) return;
    
    stopPlayer();
    const file = currentFiles[currentIndex];
    const type = file.type.startsWith('video') ? 'video' : file.type.startsWith('audio') ? 'audio' : 'image';
    const size = (file.size / (1024*1024)).toFixed(1) + ' MB';
    
    currentBlobUrl = URL.createObjectURL(file);
    
    const player = document.getElementById('player');
    let el;
    
    if (type === 'video') {
        el = document.createElement('video');
        el.controls = true;
        el.playsInline = true;
    } else if (type === 'audio') {
        el = document.createElement('audio');
        el.controls = true;
    } else {
        el = document.createElement('img');
    }
    
    el.src = currentBlobUrl;
    el.style.objectFit = currentFit;
    
    currentEl = el;
    player.appendChild(el);
    
    document.getElementById('playerCard').classList.remove('hidden');
    document.getElementById('playerInfo').textContent = file.name + ' (' + size + ')';
    document.getElementById('status').textContent = 'Wiedergabe läuft (' + (currentIndex + 1) + '/' + currentFiles.length + '): ' + file.name;
    
    if (type === 'video' || type === 'image') {
        document.getElementById('videoControls').style.display = 'flex';
    } else {
        document.getElementById('videoControls').style.display = 'none';
    }
    
    if (type !== 'image') {
        el.play().catch(err => console.log("Autoplay blockiert:", err));
    }
}

function stopPlayer() {
    if (currentEl) {
        try { currentEl.pause(); } catch(e){}
        currentEl = null;
    }
    if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl);
        currentBlobUrl = null;
    }
    const playerEl = document.getElementById('player');
    if (playerEl) {
        playerEl.innerHTML = '';
    }
    document.getElementById('playerCard').classList.add('hidden');
    document.getElementById('videoControls').style.display = 'none';
    document.getElementById('status').textContent = 'Bereit.';
}

function togglePlay() {
    if (currentEl && currentEl.play) {
        if (currentEl.paused) {
            currentEl.play();
            document.getElementById('playBtn').textContent = '⏸ Pause';
        } else {
            currentEl.pause();
            document.getElementById('playBtn').textContent = '▶ Weiter';
        }
    }
}

function prevFile() {
    if (!currentFiles.length) return;
    currentIndex = (currentIndex - 1 + currentFiles.length) % currentFiles.length;
    playCurrentFile();
}

function nextFile() {
    if (!currentFiles.length) return;
    currentIndex = (currentIndex + 1) % currentFiles.length;
    playCurrentFile();
}

function setFitMode(mode) {
    currentFit = mode;
    if (currentEl) {
        currentEl.style.objectFit = mode;
    }
    ['contain', 'cover'].forEach(m => {
        const btn = document.getElementById('btn' + m.charAt(0).toUpperCase() + m.slice(1));
        if (btn) {
            if (m === mode) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });
}

function toggleFullscreen() {
    const player = document.getElementById('player');
    if (currentEl && currentEl.requestFullscreen) {
        currentEl.requestFullscreen().catch(() => {});
    } else if (player.requestFullscreen) {
        player.requestFullscreen().catch(() => {});
    }
}
</script>
</body>
</html>
'''

    def widget():
        return {'icon': '📂', 'text': 'Mini Player', 'sub': 'Lokale Medien öffnen'}

    api.route('index', seite)
    api.widget('Mini Player', widget, ttl=60, icon='📂')
