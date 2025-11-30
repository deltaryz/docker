// this checks every 30m for an upcoming livestream on my youtube channel
// if none exists, fall back to most recent

import express from "express";
import fetch from "node-fetch";
import cors from "cors";

console.log("Stream update checker now starting...");

const app = express();
const API_KEY = process.env.YT_API_KEY;
const CHANNEL_ID = "UCcDlMox2LUcBJ6LiEqSZcBg";

app.use(cors());

let cachedVideoId = null;
let lastUpdate = null;

// do youtube api query
async function queryYouTube(eventType) {
    const url =
        "https://www.googleapis.com/youtube/v3/search" +
        `?part=snippet&channelId=${CHANNEL_ID}` +
        `&eventType=${eventType}&type=video&order=date&maxResults=1&key=${API_KEY}`;

    console.log("\nQuerying YouTube for " + eventType + "...\n" + url + "\n");

    const r = await fetch(url);
    if (!r.ok) return null;

    const j = await r.json();
    let videoId = j.items?.[0]?.id?.videoId;
    console.log("Query returned video ID: " + videoId);
    return videoId || null;
}

async function refreshCache() {
    console.log("Refreshing...");
    try {
        let vid = null;

        // 1. Check if there is a currently live stream
        vid = await queryYouTube("live");

        // 2. If none, check for the next scheduled livestream
        if (!vid) vid = await queryYouTube("upcoming");

        // 3. most recent completed livestream
        if (!vid) vid = await queryYouTube("completed");

        cachedVideoId = vid || null;
        console.log("Refreshed video ID: " + cachedVideoId)
        lastUpdate = new Date().toISOString();
    } catch (e) {
        // Do not clear cache on failure
        console.log("ERROR REFRESHING: \n" + e);
    }
}

// Startup refresh
await refreshCache();

// Refresh every 30 minutes
setInterval(refreshCache, 30 * 60 * 1000);

app.get("/yt-next", (req, res) => {
    res.json({
        videoId: cachedVideoId,
        lastUpdate
    });
});

app.listen(3001, '0.0.0.0', () => {
    console.log('Node service listening on port 3001');
});
