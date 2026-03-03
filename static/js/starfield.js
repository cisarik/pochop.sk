/**
 * Pochop — optimized starfield
 * Adaptive quality profile to keep night-sky feel with lower GPU cost.
 */
(function () {
    'use strict';

    const canvas = document.getElementById('starfield');
    if (!canvas) return;

    const ctx = canvas.getContext('2d', { alpha: true, desynchronized: true }) || canvas.getContext('2d');
    if (!ctx) return;

    const C = {
        O: [155, 176, 255],
        B: [170, 191, 255],
        A: [202, 215, 255],
        F: [248, 247, 255],
        G: [255, 244, 232],
        K: [255, 218, 181],
        M: [255, 189, 150],
    };
    const SPECTRAL = [C.F, C.F, C.A, C.A, C.B, C.G, C.G, C.K, C.O, C.M];

    let W = 0;
    let H = 0;
    let DPR = 1;
    let profile = null;
    let stars = [];
    let vivid = [];
    let bright = [];
    let dust = [];
    let dustTexture = null;
    let shootingStar = null;
    let frameId = 0;
    let resizeRaf = 0;
    let running = false;
    let lastFrameTs = 0;
    let lastShotTs = 0;
    const twinkle = {
        lastTs: 0,
        scrollOffset: 0,
        lastScrollY: 0,
        lastWheelTs: 0,
    };

    function clamp(v, min, max) {
        return Math.min(max, Math.max(min, v));
    }

    function randomRange(min, max) {
        return min + Math.random() * (max - min);
    }

    function pickProfile() {
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const coarsePointer = window.matchMedia('(pointer: coarse)').matches;
        const lowWidth = window.innerWidth < 900;
        const hwThreads = navigator.hardwareConcurrency || 4;
        const deviceMemory = navigator.deviceMemory || 4;
        const lowPower = hwThreads <= 4 || deviceMemory <= 4;

        if (reduceMotion) {
            return {
                mode: 'reduced',
                dprCap: 1,
                targetFps: 18,
                dustCount: 70,
                starCount: 95,
                vividCount: 0,
                brightCount: 2,
                shooting: false,
                shootingInterval: 22000,
                useSpikes: false,
                nebulaStatic: true,
                twinkleEnabled: true,
                twinkleMinInterval: 1100,
                twinkleIdleInterval: 1800,
                twinkleBaseBatch: 1,
                twinkleMaxBatch: 2,
                twinkleScrollOffset: 80,
                twinkleScrollCap: 1400,
                twinkleScrollGain: 1,
                twinkleFadeOutMin: 0.2,
                twinkleFadeOutMax: 0.35,
                twinkleFadeInMin: 0.08,
                twinkleFadeInMax: 0.16,
            };
        }

        if (lowPower || coarsePointer || lowWidth) {
            return {
                mode: 'lite',
                dprCap: 1.25,
                targetFps: 24,
                dustCount: 100,
                starCount: 130,
                vividCount: 6,
                brightCount: 4,
                shooting: false,
                shootingInterval: 18000,
                useSpikes: false,
                nebulaStatic: true,
                twinkleEnabled: true,
                twinkleMinInterval: 360,
                twinkleIdleInterval: 760,
                twinkleBaseBatch: 3,
                twinkleMaxBatch: 9,
                twinkleScrollOffset: 44,
                twinkleScrollCap: 5200,
                twinkleScrollGain: 4.2,
                twinkleFadeOutMin: 0.2,
                twinkleFadeOutMax: 0.4,
                twinkleFadeInMin: 0.045,
                twinkleFadeInMax: 0.1,
            };
        }

        return {
            mode: 'balanced',
            dprCap: 1.5,
            targetFps: 30,
            dustCount: 140,
            starCount: 190,
            vividCount: 14,
            brightCount: 6,
            shooting: true,
            shootingInterval: 12000,
            useSpikes: true,
            nebulaStatic: false,
            twinkleEnabled: true,
            twinkleMinInterval: 240,
            twinkleIdleInterval: 540,
            twinkleBaseBatch: 6,
            twinkleMaxBatch: 18,
            twinkleScrollOffset: 30,
            twinkleScrollCap: 7600,
            twinkleScrollGain: 5.2,
            twinkleFadeOutMin: 0.19,
            twinkleFadeOutMax: 0.42,
            twinkleFadeInMin: 0.035,
            twinkleFadeInMax: 0.085,
        };
    }

    function applyNebulaMode() {
        document.documentElement.classList.toggle('starfield-lite', profile.nebulaStatic);
    }

    function resizeCanvas() {
        W = window.innerWidth;
        H = window.innerHeight;
        DPR = Math.min(window.devicePixelRatio || 1, profile.dprCap);
        canvas.width = Math.max(1, Math.floor(W * DPR));
        canvas.height = Math.max(1, Math.floor(H * DPR));
        ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    }

    function mkDust() {
        return {
            x: Math.random() * W,
            y: Math.random() * H,
            r: 0.26 + Math.random() * 0.38,
            a: 0.08 + Math.random() * 0.16,
            color: SPECTRAL[Math.floor(Math.random() * SPECTRAL.length)],
        };
    }

    function mkStar(id) {
        return {
            id,
            x: Math.random() * W,
            y: Math.random() * H,
            r: 0.62 + Math.random() * 1.15,
            color: SPECTRAL[Math.floor(Math.random() * SPECTRAL.length)],
            baseA: 0.25 + Math.random() * 0.55,
            p1: Math.random() * 100,
            p2: Math.random() * 100,
            s1: 0.35 + Math.random() * 1.2,
            s2: 0.6 + Math.random() * 1.4,
            d1: 0.08 + Math.random() * 0.2,
            d2: 0.04 + Math.random() * 0.14,
            fade: 1,
            swapState: 0,
            swapOutDur: 0,
            swapInDur: 0,
        };
    }

    function mkVivid(id) {
        return {
            id,
            x: Math.random() * W,
            y: Math.random() * H,
            r: 0.95 + Math.random() * 1.05,
            color: SPECTRAL[Math.floor(Math.random() * 4)],
            baseA: 0.38 + Math.random() * 0.45,
            p1: Math.random() * 100,
            p2: Math.random() * 100,
            phase: Math.random() * Math.PI * 2,
            s1: 1.0 + Math.random() * 1.8,
            s2: 2.6 + Math.random() * 2.8,
            d1: 0.14 + Math.random() * 0.2,
            d2: 0.08 + Math.random() * 0.14,
            colorShift: 0.22 + Math.random() * 0.35,
        };
    }

    function mkBright(id) {
        return {
            id,
            x: Math.random() * W,
            y: Math.random() * H,
            r: 1.65 + Math.random() * 1.28,
            color: SPECTRAL[Math.floor(Math.random() * 5)],
            baseA: 0.65 + Math.random() * 0.3,
            glowR: 13 + Math.random() * 18,
            spikeLen: 8 + Math.random() * 10,
            rot: Math.random() * Math.PI,
            p1: Math.random() * 100,
            p2: Math.random() * 100,
            s1: 0.22 + Math.random() * 0.45,
            s2: 1.1 + Math.random() * 1.6,
            d1: 0.09 + Math.random() * 0.13,
            d2: 0.05 + Math.random() * 0.1,
            colorShift: 0.16 + Math.random() * 0.2,
        };
    }

    function shiftColor(base, t, seed, amount) {
        const shift = Math.sin(t * 1.1 + seed) * amount;
        return [
            clamp(base[0] + shift * 24, 0, 255),
            clamp(base[1] + shift * 8, 0, 255),
            clamp(base[2] - shift * 20, 0, 255),
        ];
    }

    function buildDustTexture() {
        const offscreen = document.createElement('canvas');
        offscreen.width = canvas.width;
        offscreen.height = canvas.height;
        const octx = offscreen.getContext('2d');
        if (!octx) return null;
        octx.setTransform(DPR, 0, 0, DPR, 0, 0);

        for (let i = 0; i < dust.length; i++) {
            const d = dust[i];
            const rgb = d.color;
            octx.beginPath();
            octx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
            octx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${d.a})`;
            octx.fill();
        }
        return offscreen;
    }

    function initLayers() {
        dust = [];
        stars = [];
        vivid = [];
        bright = [];
        for (let i = 0; i < profile.dustCount; i++) dust.push(mkDust());
        for (let i = 0; i < profile.starCount; i++) stars.push(mkStar(i));
        for (let i = 0; i < profile.vividCount; i++) vivid.push(mkVivid(i + 1000));
        for (let i = 0; i < profile.brightCount; i++) bright.push(mkBright(i + 2000));
        dustTexture = buildDustTexture();
        shootingStar = null;
    }

    function armStarSwap(star) {
        if (!star || star.swapState !== 0) return false;
        star.swapState = 1;
        star.swapOutDur = randomRange(profile.twinkleFadeOutMin, profile.twinkleFadeOutMax);
        star.swapInDur = randomRange(profile.twinkleFadeInMin, profile.twinkleFadeInMax);
        return true;
    }

    function respawnRegularStar(star) {
        const next = mkStar(star.id);
        star.x = next.x;
        star.y = next.y;
        star.r = next.r;
        star.color = next.color;
        star.baseA = next.baseA;
        star.p1 = next.p1;
        star.p2 = next.p2;
        star.s1 = next.s1;
        star.s2 = next.s2;
        star.d1 = next.d1;
        star.d2 = next.d2;
        star.fade = 0;
        star.swapState = 2;
    }

    function updateRegularStarSwap(star, dt) {
        if (star.swapState === 1) {
            const outDur = Math.max(0.01, star.swapOutDur);
            star.fade = Math.max(0, star.fade - dt / outDur);
            if (star.fade <= 0.001) {
                respawnRegularStar(star);
            }
            return;
        }
        if (star.swapState === 2) {
            const inDur = Math.max(0.01, star.swapInDur);
            star.fade = Math.min(1, star.fade + dt / inDur);
            if (star.fade >= 0.999) {
                star.fade = 1;
                star.swapState = 0;
            }
        }
    }

    function triggerTwinkleBatch(count) {
        if (count <= 0 || stars.length === 0) return;
        let armed = 0;
        const maxAttempts = Math.max(24, count * 8);
        for (let tries = 0; tries < maxAttempts && armed < count; tries++) {
            const idx = Math.floor(Math.random() * stars.length);
            if (armStarSwap(stars[idx])) armed++;
        }
    }

    function maybeTriggerTwinkle(nowTs) {
        if (!profile.twinkleEnabled || stars.length === 0) return;

        const elapsed = nowTs - twinkle.lastTs;
        if (elapsed < profile.twinkleMinInterval) return;

        const steps = Math.floor(twinkle.scrollOffset / profile.twinkleScrollOffset);
        const idleReady = elapsed >= profile.twinkleIdleInterval;
        if (steps <= 0 && !idleReady) return;

        const maxBoost = Math.max(0, profile.twinkleMaxBatch - profile.twinkleBaseBatch);
        const scrollBoost = Math.min(steps, maxBoost);
        const batchSize = clamp(
            profile.twinkleBaseBatch + scrollBoost,
            profile.twinkleBaseBatch,
            profile.twinkleMaxBatch
        );

        triggerTwinkleBatch(batchSize);
        twinkle.lastTs = nowTs;

        if (steps > 0) {
            twinkle.scrollOffset = Math.max(
                0,
                twinkle.scrollOffset - (scrollBoost + 1) * profile.twinkleScrollOffset
            );
        } else {
            twinkle.scrollOffset = Math.max(0, twinkle.scrollOffset - profile.twinkleScrollOffset * 0.35);
        }
    }

    function drawRegularStar(s, t) {
        const tw = Math.sin(t * s.s1 + s.p1) * s.d1 + Math.sin(t * s.s2 + s.p2) * s.d2;
        const fade = s.fade == null ? 1 : s.fade;
        const a = clamp((s.baseA + tw) * fade, 0.01, 1);
        if (a <= 0.012) return;
        const rgb = s.color;

        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a})`;
        ctx.fill();

        if (s.r > 0.88 && a > 0.35) {
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r * 2.9, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a * 0.06})`;
            ctx.fill();
        }
    }

    function drawVividStar(s, t) {
        const tw = Math.sin(t * s.s1 + s.p1) * s.d1 + Math.sin(t * s.s2 + s.p2) * s.d2;
        const pulse = 0.8 + 0.35 * Math.sin(t * 2.2 + s.phase);
        const a = clamp(s.baseA + tw, 0.06, 1);
        const col = shiftColor(s.color, t, s.id * 0.1, s.colorShift);

        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${a})`;
        ctx.fill();

        if (a > 0.3) {
            ctx.beginPath();
            ctx.arc(s.x, s.y, s.r * (2.2 + pulse), 0, Math.PI * 2);
            ctx.fillStyle = `rgba(${col[0]},${col[1]},${col[2]},${a * 0.08})`;
            ctx.fill();
        }
    }

    function drawBrightStar(s, t) {
        const tw = Math.sin(t * s.s1 + s.p1) * s.d1 + Math.sin(t * s.s2 + s.p2) * s.d2;
        const a = clamp(s.baseA + tw, 0.2, 1);
        const col = shiftColor(s.color, t, s.id * 0.07, s.colorShift);
        const glowR = s.glowR * (0.9 + tw * 0.3);

        const grad = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, glowR);
        grad.addColorStop(0, `rgba(${col[0]},${col[1]},${col[2]},${a * 0.18})`);
        grad.addColorStop(0.4, `rgba(${col[0]},${col[1]},${col[2]},${a * 0.05})`);
        grad.addColorStop(1, `rgba(${col[0]},${col[1]},${col[2]},0)`);
        ctx.beginPath();
        ctx.arc(s.x, s.y, glowR, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r * 1.85, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${Math.min(1, a)})`;
        ctx.fill();

        if (profile.useSpikes && a > 0.5) {
            const len = s.spikeLen * (0.85 + tw * 0.25);
            ctx.save();
            ctx.translate(s.x, s.y);
            ctx.rotate(s.rot + t * 0.02);
            ctx.strokeStyle = `rgba(${col[0]},${col[1]},${col[2]},${a * 0.18})`;
            ctx.lineWidth = 0.45;
            for (let i = 0; i < 4; i++) {
                const ang = (i * Math.PI) / 2;
                const ex = Math.cos(ang) * len;
                const ey = Math.sin(ang) * len;
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(ex, ey);
                ctx.stroke();
            }
            ctx.restore();
        }
    }

    function spawnShot() {
        return {
            x: Math.random() * W * 0.85,
            y: Math.random() * H * 0.3,
            angle: Math.PI * 0.12 + Math.random() * Math.PI * 0.2,
            speed: 300 + Math.random() * 320,
            len: 70 + Math.random() * 90,
            life: 0,
            maxLife: 0.65 + Math.random() * 0.35,
            a: 0.6 + Math.random() * 0.25,
            w: 0.9 + Math.random() * 0.9,
        };
    }

    function drawShot(shot, dt) {
        shot.life += dt;
        if (shot.life > shot.maxLife) return false;

        const p = shot.life / shot.maxLife;
        const a = shot.a * (p < 0.1 ? p / 0.1 : 1 - Math.pow((p - 0.1) / 0.9, 1.4));

        shot.x += Math.cos(shot.angle) * shot.speed * dt;
        shot.y += Math.sin(shot.angle) * shot.speed * dt;

        const tx = shot.x - Math.cos(shot.angle) * shot.len * (1 - p * 0.4);
        const ty = shot.y - Math.sin(shot.angle) * shot.len * (1 - p * 0.4);

        const trail = ctx.createLinearGradient(tx, ty, shot.x, shot.y);
        trail.addColorStop(0, 'rgba(255,255,255,0)');
        trail.addColorStop(1, `rgba(255,255,255,${a})`);
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(shot.x, shot.y);
        ctx.strokeStyle = trail;
        ctx.lineWidth = shot.w;
        ctx.lineCap = 'round';
        ctx.stroke();

        return true;
    }

    function drawFrame(t, dt, nowTs) {
        ctx.clearRect(0, 0, W, H);

        if (dustTexture) {
            ctx.drawImage(dustTexture, 0, 0, W, H);
        }

        maybeTriggerTwinkle(nowTs);

        for (let i = 0; i < stars.length; i++) {
            updateRegularStarSwap(stars[i], dt);
            drawRegularStar(stars[i], t);
        }
        for (let i = 0; i < vivid.length; i++) drawVividStar(vivid[i], t);
        for (let i = 0; i < bright.length; i++) drawBrightStar(bright[i], t);

        if (profile.shooting) {
            if (nowTs - lastShotTs > profile.shootingInterval + Math.random() * 4000) {
                shootingStar = spawnShot();
                lastShotTs = nowTs;
            }
            if (shootingStar && !drawShot(shootingStar, dt)) {
                shootingStar = null;
            }
        }
    }

    function render(ts) {
        if (!running) return;
        const frameInterval = 1000 / profile.targetFps;
        if (lastFrameTs && ts - lastFrameTs < frameInterval) {
            frameId = requestAnimationFrame(render);
            return;
        }

        const dt = lastFrameTs ? (ts - lastFrameTs) / 1000 : frameInterval / 1000;
        lastFrameTs = ts;
        drawFrame(ts / 1000, dt, ts);
        frameId = requestAnimationFrame(render);
    }

    function startLoop() {
        if (running) return;
        running = true;
        lastFrameTs = 0;
        frameId = requestAnimationFrame(render);
    }

    function stopLoop() {
        if (!running && !frameId) return;
        running = false;
        if (frameId) {
            cancelAnimationFrame(frameId);
            frameId = 0;
        }
    }

    function syncAnimationState() {
        if (document.hidden) {
            stopLoop();
            return;
        }
        startLoop();
    }

    function initScene() {
        profile = pickProfile();
        applyNebulaMode();
        resizeCanvas();
        initLayers();
        lastShotTs = 0;
        twinkle.lastTs = 0;
        twinkle.scrollOffset = 0;
        twinkle.lastScrollY = window.scrollY || window.pageYOffset || 0;
    }

    function onResize() {
        if (resizeRaf) return;
        resizeRaf = requestAnimationFrame(() => {
            resizeRaf = 0;
            initScene();
            syncAnimationState();
        });
    }

    function onScroll() {
        if (!profile || !profile.twinkleEnabled) return;
        const currentY = window.scrollY || window.pageYOffset || 0;
        const delta = Math.abs(currentY - twinkle.lastScrollY);
        twinkle.lastScrollY = currentY;
        if (delta < 1) return;
        twinkle.scrollOffset = Math.min(
            profile.twinkleScrollCap,
            twinkle.scrollOffset + delta * (profile.twinkleScrollGain || 1)
        );
        if (delta > 2) {
            twinkle.lastTs = Math.max(0, twinkle.lastTs - profile.twinkleMinInterval * 0.85);
        }
    }

    function onWheel(evt) {
        if (!profile || !profile.twinkleEnabled) return;
        const delta = Math.abs(evt.deltaY || 0);
        if (delta < 1) return;
        twinkle.scrollOffset = Math.min(
            profile.twinkleScrollCap,
            twinkle.scrollOffset + delta * (profile.twinkleScrollGain || 1)
        );
        // Make wheel-triggered twinkle feel immediate even on short pages.
        if (performance.now() - twinkle.lastWheelTs > 180) {
            twinkle.lastWheelTs = performance.now();
            twinkle.lastTs = Math.max(0, twinkle.lastTs - profile.twinkleMinInterval * 1.15);
        }
    }

    function boot() {
        initScene();
        syncAnimationState();
        window.addEventListener('resize', onResize, { passive: true });
        window.addEventListener('scroll', onScroll, { passive: true });
        window.addEventListener('wheel', onWheel, { passive: true });
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                initScene();
            }
            syncAnimationState();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
